import hmac
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, abort
from werkzeug.security import check_password_hash
from app.http_security import (
    clear_login_failures,
    get_client_ip,
    is_login_rate_limited,
    record_login_failure,
    should_enforce_csrf,
    validate_csrf_token,
)

auth_bp = Blueprint('auth', __name__)


def _verify_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False

    expected_user = current_app.config.get("ADMIN_USERNAME", "admin")
    expected_pass = current_app.config.get("ADMIN_PASSWORD", "admin")

    user = None
    try:
        from app.models import User
        user = User.query.filter_by(username=username).first()
    except Exception:
        user = None

    if user and check_password_hash(user.password_hash, password):
        return True

    # Allow env/config fallback only when no DB user exists or custom env password is configured
    if hmac.compare_digest(username, expected_user):
        if user is None or (expected_pass and expected_pass != "admin"):
            if hmac.compare_digest(password, expected_pass):
                return True
    return False


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if should_enforce_csrf() and not validate_csrf_token():
            return render_template("login.html", error="Security token expired. Refresh and try again."), 403

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        client_ip = get_client_ip()

        if is_login_rate_limited(client_ip, username):
            return render_template(
                "login.html",
                error="Too many failed login attempts. Please wait a few minutes and try again.",
            ), 429

        if _verify_credentials(username, password):
            clear_login_failures(client_ip, username)
            session["logged_in"] = True
            session["username"] = username
            session.permanent = True
            return redirect(url_for("dashboard.dashboard"))

        record_login_failure(client_ip, username)
        return render_template("login.html", error="Invalid username or password"), 401
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if should_enforce_csrf() and not validate_csrf_token():
        abort(403)
    session.pop("logged_in", None)
    session.pop("username", None)
    session.pop("csrf_token", None)
    return redirect(url_for("dashboard.index"))
