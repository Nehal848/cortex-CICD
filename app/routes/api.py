import os
import queue
from datetime import datetime
from flask import Blueprint, request, jsonify, session, send_file, Response, stream_with_context
import io

api_bp = Blueprint('api', __name__, url_prefix="/api")

# ── Shared auth guard ─────────────────────────────────────────────
def _auth():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return None

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
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    from app.services.pipeline_service import get_dashboard_stats
    return jsonify(get_dashboard_stats())

# --- PROMETHEUS ---
@api_bp.route("/prometheus/metrics")
def prometheus_metrics():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.monitoring_service import get_all_metrics
        return jsonify(get_all_metrics())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/prometheus/http_rate")
def prometheus_http_rate():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.monitoring_service import get_http_rate
        return jsonify(get_http_rate())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- DOCKER ---
@api_bp.route("/docker/containers")
def docker_containers():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify({"containers": dc.list_containers(all_containers=True), "summary": dc.get_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/docker/restart/<container_id>", methods=["POST"])
def docker_restart(container_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.restart_container(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/docker/remove/<container_id>", methods=["DELETE"])
def docker_remove(container_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.remove_container(container_id, force=True))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/docker/stats/<container_id>")
def docker_stats(container_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.get_container_stats(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- KUBERNETES ---
@api_bp.route("/k8s/pods")
def k8s_pods():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"pods": k8s.list_pods(ns), "summary": k8s.get_cluster_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/nodes")
def k8s_nodes():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        return jsonify({"nodes": k8s.list_nodes()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/deployments")
def k8s_deployments():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"deployments": k8s.list_deployments(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/services")
def k8s_services():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"services": k8s.list_services(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/k8s/restart/<pod_name>", methods=["POST"])
def k8s_restart_pod(pod_name):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
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
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"jobs": jc.get_all_jobs()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/jenkins/trigger/<path:job_name>", methods=["POST"])
def jenkins_trigger(job_name):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import jenkins_client as jc
        return jsonify(jc.trigger_build(job_name, request.json or None))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/jenkins/log/<path:job_name>/<int:build_num>")
def jenkins_log(job_name, build_num):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"log": jc.get_console_log(job_name, build_num)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- ML ---
@api_bp.route("/predict/<run_id>")
def api_predict(run_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.prediction_service import get_prediction_for_run
        return jsonify(get_prediction_for_run(run_id))
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
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.healing_service import trigger_healing_now
        return jsonify(trigger_healing_now(run_id, request.json or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/healing/status")
def api_healing_status():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.healing_service import get_healing_status
        return jsonify(get_healing_status())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- TEE ---
@api_bp.route("/tee/status")
def tee_status():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.tee import secrets as tee_secrets
        return jsonify(tee_secrets.get_tee_summary())
    except Exception as exc:
        return jsonify({"error": str(exc), "overall_status": "Error"}), 500

@api_bp.route("/tee/attestation")
def tee_attestation():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.tee import attestation
        return jsonify(attestation.generate_attestation_report(request.args.get("nonce", None)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/tee/seal", methods=["POST"])
def tee_seal():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
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
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
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
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.security import secret_scanner
        return jsonify(secret_scanner.scan_directory(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# --- REPORTS ---
@api_bp.route("/reports/pipeline")
def report_pipeline():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.report_service import build_pipeline_report
        data, mime, ext = build_pipeline_report()
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_pipeline_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@api_bp.route("/reports/healing")
def report_healing():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
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

@api_bp.route("/stream")
def sse_stream():
    """
    Server-Sent Events endpoint.
    Returns a persistent text/event-stream connection that pushes
    real-time events to the browser without page refresh.

    Authentication: session cookie (same as all other API endpoints).
    Disconnect: close the browser tab or EventSource.close().
    """
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    from app.events import subscribe, unsubscribe
    import json as _json

    sub_id, q = subscribe()

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
