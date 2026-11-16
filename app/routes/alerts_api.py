from flask import Blueprint, jsonify, request

from app.auth_guard import _auth, check_role

alerts_api_bp = Blueprint('alerts_api', __name__, url_prefix="/api")


@alerts_api_bp.route("/alerts/active")
def alerts_active():
    """GET /api/alerts/active — Active + Acknowledged alerts."""
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.alert_service import get_active_alerts
        return jsonify({"alerts": get_active_alerts()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@alerts_api_bp.route("/alerts/history")
def alerts_history():
    """GET /api/alerts/history?page=1&per_page=20 — Resolved + Archived."""
    auth = _auth()
    if auth:
        return auth
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        from app.services.alert_service import get_alert_history
        return jsonify(get_alert_history(page, per_page))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@alerts_api_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def alert_acknowledge(alert_id):
    """POST /api/alerts/<id>/acknowledge — Active → Acknowledged."""
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        user = (request.json or {}).get("user", "admin")
        from app.services.alert_service import acknowledge_alert
        result, status = acknowledge_alert(alert_id, user)
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@alerts_api_bp.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
def alert_resolve(alert_id):
    """POST /api/alerts/<id>/resolve — Active|Acknowledged|Silenced → Resolved."""
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        user = (request.json or {}).get("user", "admin")
        from app.services.alert_service import resolve_alert
        result, status = resolve_alert(alert_id, user)
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@alerts_api_bp.route("/alerts/<int:alert_id>/silence", methods=["POST"])
def alert_silence(alert_id):
    """POST /api/alerts/<id>/silence — Silences for duration_minutes."""
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.validation import validate_alert_silence
        cleaned, errors = validate_alert_silence(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        from app.services.alert_service import silence_alert
        result, status = silence_alert(alert_id, cleaned["duration_minutes"])
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@alerts_api_bp.route("/alerts/<int:alert_id>/archive", methods=["POST"])
def alert_archive(alert_id):
    """POST /api/alerts/<id>/archive — Resolved → Archived."""
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("admin")
    if role_err:
        return role_err
    try:
        from app.services.alert_service import archive_alert
        result, status = archive_alert(alert_id)
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
