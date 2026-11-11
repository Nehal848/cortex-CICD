import hashlib
import hmac
import io
import os
import queue
import secrets
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    jsonify,
    request,
    send_file,
    session,
    stream_with_context,
)
from app.http_security import get_client_ip, should_enforce_csrf, validate_csrf_token

api_bp = Blueprint('api', __name__, url_prefix="/api")

# ── Shared auth guard (Session Cookie + CSRF OR Bearer / X-API-Key) ─
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

# --- PIPELINE ---
@api_bp.route("/pipeline/run", methods=["POST"])
def run_pipeline():
    auth = _auth()
    if auth:
        return auth
    data = request.json or {}
    # Input validation
    from app.validation import validate_pipeline_run
    cleaned, errors = validate_pipeline_run(data)
    if errors:
        return jsonify({"errors": errors}), 400
    from app.services.pipeline_service import trigger_pipeline
    result = trigger_pipeline(cleaned["job_name"], cleaned["branch"])
    
    run = result["run"]
    return jsonify({
        "success": True,
        "message": result["message"],
        "mock": result["mock"],
        "jenkins_result": result["jenkins_result"],
        "run": {
            "id": run.run_id,
            "repo": run.repo,
            "branch": run.branch,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "timestamp": run.timestamp,
        }
    })

@api_bp.route("/stats")
def api_stats():
    auth = _auth()
    if auth:
        return auth
    from app.services.pipeline_service import get_dashboard_stats
    return jsonify(get_dashboard_stats())

# --- PROMETHEUS ---
@api_bp.route("/prometheus/metrics")
def prometheus_metrics():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.monitoring_service import get_all_metrics
        return jsonify(get_all_metrics())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/prometheus/http_rate")
def prometheus_http_rate():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.monitoring_service import get_http_rate
        return jsonify(get_http_rate())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- DOCKER ---
@api_bp.route("/docker/containers")
def docker_containers():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import docker_client as dc
        return jsonify({"containers": dc.list_containers(all_containers=True), "summary": dc.get_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/docker/restart/<container_id>", methods=["POST"])
def docker_restart(container_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.restart_container(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/docker/remove/<container_id>", methods=["DELETE"])
def docker_remove(container_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.remove_container(container_id, force=True))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/docker/stats/<container_id>")
def docker_stats(container_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.get_container_stats(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- KUBERNETES ---
@api_bp.route("/k8s/pods")
def k8s_pods():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"pods": k8s.list_pods(ns), "summary": k8s.get_cluster_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/nodes")
def k8s_nodes():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        return jsonify({"nodes": k8s.list_nodes()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/deployments")
def k8s_deployments():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"deployments": k8s.list_deployments(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/services")
def k8s_services():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"services": k8s.list_services(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/restart/<pod_name>", methods=["POST"])
def k8s_restart_pod(pod_name):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.json.get("namespace", "default") if request.json else "default"
        return jsonify(k8s.restart_pod(pod_name, ns))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/scale/<deployment_name>", methods=["POST"])
def k8s_scale(deployment_name):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        from app.validation import validate_k8s_scale
        cleaned, errors = validate_k8s_scale(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        return jsonify(k8s.scale_deployment(
            deployment_name, cleaned["replicas"], cleaned["namespace"]
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- JENKINS ---
@api_bp.route("/jenkins/jobs")
def jenkins_jobs():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"jobs": jc.get_all_jobs()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/jenkins/trigger/<path:job_name>", methods=["POST"])
def jenkins_trigger(job_name):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import jenkins_client as jc
        return jsonify(jc.trigger_build(job_name, request.json or None))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/jenkins/log/<path:job_name>/<int:build_num>")
def jenkins_log(job_name, build_num):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"log": jc.get_console_log(job_name, build_num)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- ML ---
@api_bp.route("/predict/<run_id>")
def api_predict(run_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.prediction_service import get_prediction_for_run
        return jsonify(get_prediction_for_run(run_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/ml/retrain", methods=["POST"])
def api_ml_retrain():
    auth = _auth()
    if auth:
        return auth
    try:
        from ml.predict_failure import retrain_from_database
        min_samples = int((request.json or {}).get("min_samples", 5))
        return jsonify(retrain_from_database(min_samples=min_samples))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/analyze", methods=["POST"])
def api_analyze():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.validation import validate_analyze
        cleaned, errors = validate_analyze(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        from app.services.prediction_service import analyze_failure
        return jsonify(analyze_failure(
            cleaned["failure_type"],
            cleaned["log_snippet"],
            cleaned["run_id"],
            cleaned["pod_restarts"],
            cleaned["risk_score"],
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- HEALING ---
@api_bp.route("/heal/<run_id>", methods=["POST"])
def api_heal(run_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.healing_service import trigger_healing_now
        return jsonify(trigger_healing_now(run_id, request.json or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/healing/status")
def api_healing_status():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.healing_service import get_healing_status
        return jsonify(get_healing_status())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- TEE ---
@api_bp.route("/tee/status")
def tee_status():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.tee import secrets as tee_secrets
        return jsonify(tee_secrets.get_tee_summary())
    except Exception as exc:
        return jsonify({"error": str(exc), "overall_status": "Error"}), 500

@api_bp.route("/tee/attestation")
def tee_attestation():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.tee import attestation
        return jsonify(attestation.generate_attestation_report(request.args.get("nonce", None)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/tee/seal", methods=["POST"])
def tee_seal():
    auth = _auth()
    if auth:
        return auth
    try:
        data = request.json or {}
        if not data.get("key") or not data.get("value"):
            return jsonify({"error": "key and value required"}), 400
        from app.tee import secure_storage
        return jsonify({"success": secure_storage.store_secret(data["key"], data["value"]), "message": f"Secret '{data['key']}' sealed."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/tee/secrets")
def tee_secrets_list():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.tee import secure_storage
        return jsonify(secure_storage.get_store_info())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- SECURITY ---
@api_bp.route("/security/scan", methods=["POST"])
def security_scan():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.validation import validate_security_scan
        cleaned, errors = validate_security_scan(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        from app.security import scanner
        result = scanner.scan_image(cleaned["image"])
        if result.get("critical", 0) > 0:
            from app.services.notification_service import notify_security_issue
            notify_security_issue(cleaned["image"], result["critical"], result["high"])
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/security/secrets")
def security_secrets_scan():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.security import secret_scanner
        return jsonify(secret_scanner.scan_directory(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/security/sbom", methods=["POST"])
def security_sbom():
    """Generate an SBOM for a container image via Syft."""
    auth = _auth()
    if auth:
        return auth
    try:
        from app.validation import validate_security_scan, validate_sbom_format
        body = request.json or {}
        cleaned, errors = validate_security_scan(body)
        output_format, fmt_err = validate_sbom_format(body.get("format", "spdx-json"))
        if fmt_err:
            errors.append(fmt_err)
        if errors:
            return jsonify({"errors": errors}), 400
        from app.security import sbom
        return jsonify(sbom.generate_sbom(cleaned["image"], output_format))
    except Exception as exc:
        return jsonify({"error": "SBOM generation failed."}), 500

@api_bp.route("/security/cosign/verify", methods=["POST"])
def security_cosign_verify():
    """Verify cryptographic image signature via Cosign."""
    auth = _auth()
    if auth:
        return auth
    try:
        from app.validation import validate_security_scan, validate_cosign_public_key
        body = request.json or {}
        cleaned, errors = validate_security_scan(body)
        public_key, key_err = validate_cosign_public_key(body.get("public_key"))
        if key_err:
            errors.append(key_err)
        if errors:
            return jsonify({"errors": errors}), 400
        from app.security import cosign
        return jsonify(cosign.verify_image_signature(cleaned["image"], public_key))
    except Exception as exc:
        return jsonify({"error": "Signature verification failed."}), 500

# --- REPORTS ---
@api_bp.route("/reports/pipeline")
def report_pipeline():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.report_service import build_pipeline_report
        data, mime, ext = build_pipeline_report()
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_pipeline_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/reports/healing")
def report_healing():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.report_service import build_healing_report
        data, mime, ext = build_healing_report()
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_healing_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/reports/ai/<run_id>")
def report_ai(run_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.report_service import build_ai_report
        data, mime, ext = build_ai_report(run_id)
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_ai_report_{run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# =================================================================
# ALERT LIFECYCLE  (v1.2)
# =================================================================

@api_bp.route("/alerts/active")
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


@api_bp.route("/alerts/history")
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


@api_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def alert_acknowledge(alert_id):
    """POST /api/alerts/<id>/acknowledge — Active → Acknowledged."""
    auth = _auth()
    if auth:
        return auth
    try:
        user = (request.json or {}).get("user", "admin")
        from app.services.alert_service import acknowledge_alert
        result, status = acknowledge_alert(alert_id, user)
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
def alert_resolve(alert_id):
    """POST /api/alerts/<id>/resolve — Active|Acknowledged|Silenced → Resolved."""
    auth = _auth()
    if auth:
        return auth
    try:
        user = (request.json or {}).get("user", "admin")
        from app.services.alert_service import resolve_alert
        result, status = resolve_alert(alert_id, user)
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/alerts/<int:alert_id>/silence", methods=["POST"])
def alert_silence(alert_id):
    """POST /api/alerts/<id>/silence — Silences for duration_minutes."""
    auth = _auth()
    if auth:
        return auth
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


@api_bp.route("/alerts/<int:alert_id>/archive", methods=["POST"])
def alert_archive(alert_id):
    """POST /api/alerts/<id>/archive — Resolved → Archived."""
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.alert_service import archive_alert
        result, status = archive_alert(alert_id)
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# =================================================================
# SSE LIVE STREAM  (v1.2)
# GET /api/stream  — text/event-stream, auth required
# =================================================================

# --- PLATFORM SETTINGS & API TOKENS ---
_BOOL_SETTINGS = {
    "slack_notifications",
    "pagerduty_escalation",
    "auto_rollback",
    "auto_restart_pods",
}
_PCT_SETTINGS = {"cpu_threshold", "memory_threshold"}
_URL_SETTINGS = {"jenkins_url", "prometheus_url"}


@api_bp.route("/settings", methods=["GET", "POST"])
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


@api_bp.route("/auth/token", methods=["POST", "DELETE"])
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


@api_bp.route("/stream")
def sse_stream():
    """
    Server-Sent Events endpoint.
    Returns a persistent text/event-stream connection that pushes
    real-time events to the browser without page refresh.

    Authentication: session cookie or Bearer token.
    Disconnect: close the browser tab or EventSource.close().
    """
    auth = _auth()
    if auth:
        return auth

    from app.events import subscribe, unsubscribe
    import json as _json

    client_ip = get_client_ip()
    try:
        sub_id, q = subscribe(client_ip)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 429

    @stream_with_context
    def _generate():
        # Initial connection event
        yield f"event: connected\ndata: {_json.dumps({'message': 'SSE stream connected', 'client_id': sub_id})}\n\n"
        try:
            while True:
                try:
                    item = q.get(timeout=30)
                    yield f"event: {item['event']}\ndata: {item['data']}\n\n"
                except queue.Empty:
                    # Heartbeat comment keeps the connection alive through proxies
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            unsubscribe(sub_id)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx response buffering
            "Connection":       "keep-alive",
        },
    )
