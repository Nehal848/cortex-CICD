import hashlib
import hmac
import os
from datetime import datetime
from functools import wraps

from flask import current_app, g, jsonify, request, session

from app.http_security import should_enforce_csrf, validate_csrf_token


def _extract_api_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-API-Key", "").strip()


def _auth():
    if session.get("logged_in"):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and should_enforce_csrf():
            if not validate_csrf_token():
                return jsonify({"error": "CSRF validation failed"}), 403
        g.api_user = session.get("username", "admin")
        return None

    token = _extract_api_token()
    if token:
        configured = current_app.config.get("CORTEX_API_TOKEN") or os.getenv("CORTEX_API_TOKEN", "")
        if configured and hmac.compare_digest(token, configured):
            g.api_user = "api-token"
            return None

        try:
            from app.models import User
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            users = User.query.filter(User.api_token_hash.isnot(None)).all()
            now = datetime.utcnow()
            for user in users:
                if hmac.compare_digest(user.api_token_hash, token_hash):
                    if user.api_token_expires_at and user.api_token_expires_at < now:
                        return jsonify({"error": "API token expired"}), 401
                    g.api_user = user.username
                    return None
        except Exception:
            pass

    return jsonify({"error": "Unauthorized"}), 401


ROLE_LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


def require_role(min_role: str):
    """Decorator to enforce minimum role level on an API route."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = g.get("api_user_role", "admin")  # default admin for backward compat
            if ROLE_LEVELS.get(user_role, 0) < ROLE_LEVELS.get(min_role, 1):
                return jsonify({"error": "Insufficient permissions", "required": min_role}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        err = _auth()
        if err:
            return err
        return f(*args, **kwargs)
    return decorated
