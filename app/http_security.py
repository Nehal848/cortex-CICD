"""
Shared HTTP security helpers for CortexCICD.

Provides:
- Trusted-proxy-aware client IP extraction (`get_client_ip`)
- Per-session CSRF token management & validation (`get_csrf_token`, `validate_csrf`)
- Thread-safe sliding-window login brute-force rate limiting
"""

from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from collections import defaultdict
from flask import current_app, request, session

_login_lock = threading.Lock()
_failed_logins: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SECS = 300   # 5 minutes
_MAX_FAILURES_PER_PAIR = 5
_MAX_FAILURES_PER_IP = 15


def get_client_ip() -> str:
    """
    Resolve client IP safely. Only trusts X-Forwarded-For up to
    TRUSTED_PROXY_COUNT hops; otherwise returns socket remote_addr.
    """
    try:
        trusted = int(current_app.config.get("TRUSTED_PROXY_COUNT", os.getenv("TRUSTED_PROXY_COUNT", "0")))
    except (TypeError, ValueError):
        trusted = 0

    remote = request.remote_addr or "127.0.0.1"
    if trusted > 0:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                idx = max(0, len(parts) - trusted)
                return parts[idx]
    return remote


def get_csrf_token() -> str:
    """Return current session CSRF token, generating one on first access."""
    tok = session.get("csrf_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf_token"] = tok
    return tok


def should_enforce_csrf() -> bool:
    """
    Enforce CSRF in production/non-test requests, or when ENFORCE_CSRF=True
    is explicitly requested (e.g. automated CSRF security tests).
    """
    if current_app.config.get("ENFORCE_CSRF"):
        return True
    if current_app.config.get("TESTING"):
        return False
    return os.getenv("DISABLE_CSRF", "false").lower() not in ("true", "1")


def validate_csrf_token(presented: str | None = None) -> bool:
    """Validate presented CSRF header/form token against session token."""
    expected = session.get("csrf_token")
    if not expected:
        return False
    token = (
        presented
        or request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or ""
    ).strip()
    return bool(token) and hmac.compare_digest(token, expected)


def _prune(timestamps: list[float], now: float) -> list[float]:
    cutoff = now - _LOGIN_WINDOW_SECS
    return [ts for ts in timestamps if ts > cutoff]


def is_login_rate_limited(client_ip: str, username: str) -> bool:
    """Return True if client IP or (IP, username) exceeded failed attempts."""
    now = time.monotonic()
    ip_key = f"ip:{client_ip}"
    pair_key = f"pair:{client_ip}:{username.lower()}"
    with _login_lock:
        _failed_logins[ip_key] = _prune(_failed_logins[ip_key], now)
        _failed_logins[pair_key] = _prune(_failed_logins[pair_key], now)
        return (
            len(_failed_logins[pair_key]) >= _MAX_FAILURES_PER_PAIR
            or len(_failed_logins[ip_key]) >= _MAX_FAILURES_PER_IP
        )


def record_login_failure(client_ip: str, username: str) -> None:
    """Record a failed login timestamp for brute-force throttling."""
    now = time.monotonic()
    with _login_lock:
        _failed_logins[f"ip:{client_ip}"].append(now)
        _failed_logins[f"pair:{client_ip}:{username.lower()}"].append(now)


def clear_login_failures(client_ip: str, username: str) -> None:
    """Reset failure counter after a successful login."""
    with _login_lock:
        _failed_logins.pop(f"pair:{client_ip}:{username.lower()}", None)

