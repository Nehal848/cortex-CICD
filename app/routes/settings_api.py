import hashlib
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request, session

from app.auth_guard import _auth, check_role

settings_api_bp = Blueprint('settings_api', __name__, url_prefix="/api")

_BOOL_SETTINGS = {
    "slack_notifications",
    "pagerduty_escalation",
    "auto_rollback",
    "auto_restart_pods",
}
_PCT_SETTINGS = {"cpu_threshold", "memory_threshold"}
_URL_SETTINGS = {"jenkins_url", "prometheus_url"}


@settings_api_bp.route("/settings", methods=["GET", "POST"])
def platform_settings():
    """GET or update persisted platform settings in database."""
    auth = _auth()
    if auth:
        return auth

    from app.db import db
    from app.models import PlatformSetting

    if request.method == "GET":
        rows = PlatformSetting.query.order_by(PlatformSetting.key.asc()).all()
        return jsonify({"settings": {row.key: row.value for row in rows}}), 200

    role_err = check_role("admin")
    if role_err:
        return role_err

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "JSON object of settings is required."}), 400

    # Accept either flat dict {"cpu_threshold": 80} or {"settings": {...}}
    updates = data.get("settings") if isinstance(data.get("settings"), dict) else data
    if not updates:
        return jsonify({"error": "No valid setting fields provided."}), 400

    cleaned = {}
    for key, raw_val in updates.items():
        if key in _BOOL_SETTINGS:
            if isinstance(raw_val, bool):
                cleaned[key] = "true" if raw_val else "false"
            elif isinstance(raw_val, str) and raw_val.strip().lower() in ("true", "false", "1", "0", "on", "off"):
                cleaned[key] = "true" if raw_val.strip().lower() in ("true", "1", "on") else "false"
            else:
                return jsonify({"error": f"Invalid boolean value for '{key}'."}), 400
        elif key in _PCT_SETTINGS:
            try:
                pct = int(raw_val)
            except (TypeError, ValueError):
                return jsonify({"error": f"'{key}' must be an integer between 1 and 100."}), 400
            if not (1 <= pct <= 100):
                return jsonify({"error": f"'{key}' must be between 1 and 100."}), 400
            cleaned[key] = str(pct)
        elif key in _URL_SETTINGS:
            from app.validation import validate_service_url
            safe_url, url_err = validate_service_url(raw_val, key)
            if url_err:
                return jsonify({"error": url_err}), 400
            cleaned[key] = safe_url
        else:
            return jsonify({"error": f"Unknown setting key: '{key}'"}), 400

    for key, val in cleaned.items():
        row = PlatformSetting.query.filter_by(key=key).first()
        if row:
            row.value = val
            row.updated_at = datetime.utcnow()
        else:
            db.session.add(PlatformSetting(key=key, value=val))
    db.session.commit()

    all_rows = PlatformSetting.query.order_by(PlatformSetting.key.asc()).all()
    return jsonify({
        "status": "saved",
        "updated": list(cleaned.keys()),
        "settings": {row.key: row.value for row in all_rows},
    }), 200


@settings_api_bp.route("/auth/token", methods=["POST", "DELETE"])
def manage_api_token():
    """Generate (POST) or revoke (DELETE) a scoped Bearer API token for the active user."""
    auth = _auth()
    if auth:
        return auth

    from app.db import db
    from app.models import User

    username = session.get("username") or getattr(g, "api_user", None) or current_app.config.get("ADMIN_USERNAME", "admin")
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User.query.filter_by(role="admin").first()
    if not user:
        return jsonify({"error": "No user record found to bind token."}), 404

    if request.method == "DELETE":
        user.api_token_hash = None
        user.api_token_expires_at = None
        db.session.commit()
        return jsonify({"status": "revoked", "username": user.username}), 200

    body = request.get_json(silent=True) or {}
    try:
        expires_days = int(body.get("expires_days", 30))
    except (TypeError, ValueError):
        return jsonify({"error": "'expires_days' must be an integer between 1 and 365."}), 400
    if not (1 <= expires_days <= 365):
        return jsonify({"error": "'expires_days' must be between 1 and 365."}), 400

    raw_token = "cx_" + secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=expires_days)
    user.api_token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    user.api_token_expires_at = expires_at
    db.session.commit()

    return jsonify({
        "token": raw_token,
        "username": user.username,
        "expires_at": expires_at.isoformat() + "Z",
        "header_example": f"Authorization: Bearer {raw_token}",
    }), 200


@settings_api_bp.route("/users", methods=["GET", "POST"])
def manage_users():
    """List all users (GET) or create a new user (POST). Admin only."""
    auth = _auth()
    if auth:
        return auth

    from app.auth_guard import require_role
    from app.db import db
    from app.models import User
    from werkzeug.security import generate_password_hash

    current_role = User.get_role(session.get("username") or getattr(g, "api_user", "admin"))
    if current_role != "admin":
        return jsonify({"error": "Admin role required to manage users."}), 403

    if request.method == "GET":
        users = User.query.order_by(User.id.asc()).all()
        return jsonify({
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "role": u.role,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "has_api_token": bool(u.api_token_hash),
                    "token_expires_at": u.api_token_expires_at.isoformat() if u.api_token_expires_at else None,
                }
                for u in users
            ]
        }), 200

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    role = (data.get("role") or "viewer").strip().lower()

    if not username or len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if role not in ("admin", "operator", "viewer"):
        return jsonify({"error": "Role must be one of: admin, operator, viewer."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": f"User '{username}' already exists."}), 409

    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        "status": "created",
        "username": new_user.username,
        "role": new_user.role,
    }), 201


@settings_api_bp.route("/users/<username>", methods=["DELETE"])
def delete_user(username: str):
    """Delete a user account. Admin only."""
    auth = _auth()
    if auth:
        return auth

    from app.db import db
    from app.models import User

    caller_username = session.get("username") or getattr(g, "api_user", "admin")
    if User.get_role(caller_username) != "admin":
        return jsonify({"error": "Admin role required to delete users."}), 403

    if caller_username == username:
        return jsonify({"error": "Cannot delete your own active account."}), 400

    target = User.query.filter_by(username=username).first()
    if not target:
        return jsonify({"error": f"User '{username}' not found."}), 404

    if target.role == "admin":
        admin_count = User.query.filter_by(role="admin").count()
        if admin_count <= 1:
            return jsonify({"error": "Cannot delete the sole administrator account."}), 400

    db.session.delete(target)
    db.session.commit()
    return jsonify({"status": "deleted", "username": username}), 200

