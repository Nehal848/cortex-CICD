import os
import sys
from datetime import datetime
from flask import (render_template, request, jsonify, redirect,
                   url_for, session, send_file)
from . import main_bp
from ..db import db
from ..models import PipelineRun, Deployment, HealingEvent, Alert

# ── Project root on path ───────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Auth helper ────────────────────────────────────────────────────
def _require_login():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return None


# ═══════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == "admin" and password == "admin":
            session["logged_in"] = True
            return redirect(url_for("main.dashboard"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("main.index"))


@main_bp.route("/docs")
def docs():
    return render_template("docs.html")


# ═══════════════════════════════════════════════════════════════════
# PROTECTED PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/dashboard")
def dashboard():
    redir = _require_login()
    if redir: return redir

    runs        = PipelineRun.query.order_by(PipelineRun.created_at.desc()).limit(8).all()
    total_runs  = PipelineRun.query.count()
    failed      = PipelineRun.query.filter_by(status="Failed").count()
    healed      = PipelineRun.query.filter_by(status="Healed").count()
    success     = PipelineRun.query.filter_by(status="Success").count()
    total_deps  = Deployment.query.count()
    active_alerts = Alert.query.filter_by(status="Active").count()
    success_rate  = round((success + healed) / total_runs * 100, 1) if total_runs else 0

    return render_template("dashboard.html",
        active_page="dashboard",
        runs=runs,
        stats={
            "total_runs":    total_runs,
            "failed":        failed,
            "healed":        healed,
            "success_rate":  success_rate,
            "total_deps":    total_deps,
            "active_alerts": active_alerts,
        }
    )


@main_bp.route("/pipeline")
def pipeline():
    redir = _require_login()
    if redir: return redir
    runs = PipelineRun.query.order_by(PipelineRun.created_at.desc()).all()
    return render_template("pipeline.html", active_page="pipeline", runs=runs)


@main_bp.route("/deployments")
def deployments():
    redir = _require_login()
    if redir: return redir
    deps = Deployment.query.order_by(Deployment.created_at.desc()).all()
    return render_template("deployments.html", active_page="deployments", deployments=deps)


@main_bp.route("/self-healing")
def self_healing():
    redir = _require_login()
    if redir: return redir
    events = HealingEvent.query.order_by(HealingEvent.created_at.desc()).all()
    return render_template("self_healing.html", active_page="self_healing", events=events)


@main_bp.route("/kubernetes")
def kubernetes():
    redir = _require_login()
    if redir: return redir
    return render_template("kubernetes.html", active_page="kubernetes")


@main_bp.route("/monitoring")
def monitoring():
    redir = _require_login()
    if redir: return redir
    return render_template("monitoring.html", active_page="monitoring")


@main_bp.route("/logs")
def logs():
    redir = _require_login()
    if redir: return redir
    runs = PipelineRun.query.order_by(PipelineRun.created_at.desc()).limit(20).all()
    return render_template("logs.html", active_page="logs", runs=runs)


@main_bp.route("/prediction")
def prediction():
    redir = _require_login()
    if redir: return redir
    runs = PipelineRun.query.order_by(PipelineRun.risk_score.desc()).limit(10).all()
    return render_template("prediction.html", active_page="prediction", runs=runs)


@main_bp.route("/alerts")
def alerts():
    redir = _require_login()
    if redir: return redir
    all_alerts = Alert.query.order_by(Alert.created_at.desc()).all()
    return render_template("alerts.html", active_page="alerts", alerts=all_alerts)


@main_bp.route("/settings")
def settings():
    redir = _require_login()
    if redir: return redir
    return render_template("settings.html", active_page="settings")


@main_bp.route("/tee")
def tee():
    redir = _require_login()
    if redir: return redir
    return render_template("tee.html", active_page="tee")


# ═══════════════════════════════════════════════════════════════════
# ORIGINAL API — Pipeline & Stats
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/pipeline/run", methods=["POST"])
def run_pipeline():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    data     = request.json or {}
    job_name = data.get("job_name", "CortexCICD/Self-Healing-CI-CD")
    branch   = data.get("branch", "main")

    # ── Trigger real Jenkins build (falls back to mock automatically) ─
    jenkins_result = {}
    try:
        from app.integrations import jenkins_client as jc
        jenkins_result = jc.trigger_build(job_name, {"BRANCH": branch} if branch else None)
    except Exception as exc:
        jenkins_result = {"success": False, "message": str(exc), "mock": True}

    # ── Create DB record ───────────────────────────────────────────────
    last    = PipelineRun.query.order_by(PipelineRun.id.desc()).first()
    new_num = int(last.run_id.split("-")[1]) + 1 if last else 4820
    new_run = PipelineRun(
        run_id=f"RUN-{new_num}", repo="CortexCICD/Self-Healing-CI-CD",
        branch=branch, status="In Progress", triggered_by="Manual",
        duration_secs=0, risk_score=0, created_at=datetime.utcnow(),
    )
    db.session.add(new_run)
    db.session.commit()

    return jsonify({
        "success":        True,
        "message":        jenkins_result.get("message", "Pipeline run triggered."),
        "mock":           jenkins_result.get("mock", False),
        "jenkins_result": jenkins_result,
        "run": {
            "id":           new_run.run_id,
            "repo":         new_run.repo,
            "branch":       new_run.branch,
            "status":       new_run.status,
            "triggered_by": new_run.triggered_by,
            "timestamp":    new_run.timestamp,
        }
    })


@main_bp.route("/api/stats")
def api_stats():
    """JSON stats used by dashboard JS for live telemetry."""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    total   = PipelineRun.query.count()
    failed  = PipelineRun.query.filter_by(status="Failed").count()
    healed  = PipelineRun.query.filter_by(status="Healed").count()
    success = PipelineRun.query.filter_by(status="Success").count()
    rate    = round((success + healed) / total * 100, 1) if total else 0
    return jsonify({
        "total_runs":    total,
        "failed_builds": failed,
        "healed_runs":   healed,
        "success_rate":  rate,
        "total_deps":    Deployment.query.count(),
        "active_alerts": Alert.query.filter_by(status="Active").count(),
    })


# ═══════════════════════════════════════════════════════════════════
# PROMETHEUS METRICS API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/prometheus/metrics")
def prometheus_metrics():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import prometheus_client as pc
        return jsonify(pc.get_all_metrics())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/prometheus/http_rate")
def prometheus_http_rate():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import prometheus_client as pc
        return jsonify({
            "requests_per_sec": pc.get_http_request_rate(),
            "error_rate":       pc.get_error_rate(),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# DOCKER API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/docker/containers")
def docker_containers():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        containers = dc.list_containers(all_containers=True)
        summary    = dc.get_summary()
        return jsonify({"containers": containers, "summary": summary})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/docker/restart/<container_id>", methods=["POST"])
def docker_restart(container_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.restart_container(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/docker/remove/<container_id>", methods=["DELETE"])
def docker_remove(container_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.remove_container(container_id, force=True))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/docker/stats/<container_id>")
def docker_stats(container_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.get_container_stats(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# KUBERNETES API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/k8s/pods")
def k8s_pods():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"pods": k8s.list_pods(ns), "summary": k8s.get_cluster_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/k8s/nodes")
def k8s_nodes():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        return jsonify({"nodes": k8s.list_nodes()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/k8s/deployments")
def k8s_deployments():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"deployments": k8s.list_deployments(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/k8s/services")
def k8s_services():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"services": k8s.list_services(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/k8s/restart/<pod_name>", methods=["POST"])
def k8s_restart_pod(pod_name):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        ns = request.json.get("namespace", "default") if request.json else "default"
        return jsonify(k8s.restart_pod(pod_name, ns))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/k8s/scale/<deployment_name>", methods=["POST"])
def k8s_scale(deployment_name):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import k8s_client as k8s
        data     = request.json or {}
        replicas = int(data.get("replicas", 1))
        ns       = data.get("namespace", "default")
        return jsonify(k8s.scale_deployment(deployment_name, replicas, ns))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# JENKINS API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/jenkins/jobs")
def jenkins_jobs():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"jobs": jc.get_all_jobs()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/jenkins/trigger/<path:job_name>", methods=["POST"])
def jenkins_trigger(job_name):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import jenkins_client as jc
        params = request.json or {}
        return jsonify(jc.trigger_build(job_name, params or None))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/jenkins/log/<path:job_name>/<int:build_num>")
def jenkins_log(job_name, build_num):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.integrations import jenkins_client as jc
        log = jc.get_console_log(job_name, build_num)
        return jsonify({"log": log})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# ML PREDICTION & ROOT CAUSE ANALYSIS API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/predict/<run_id>")
def api_predict(run_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        run = PipelineRun.query.filter_by(run_id=run_id).first()
        if not run:
            return jsonify({"error": "Run not found"}), 404

        from ml.predict_failure import predict_failure_risk
        prediction = predict_failure_risk(
            repo=run.repo,
            branch=run.branch,
            files_changed=request.args.get("files_changed", 10, type=int),
            duration_secs=run.duration_secs,
        )
        prediction["run_id"] = run_id
        return jsonify(prediction)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Root cause analysis for a failure."""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data         = request.json or {}
        failure_type = data.get("failure_type", "")
        log_snippet  = data.get("log_snippet", "")
        run_id       = data.get("run_id", "")
        pod_restarts = data.get("pod_restarts", 0)
        risk_score   = data.get("risk_score", 0)

        from ml.root_cause import analyze, analyze_risk_factors
        rca = analyze(failure_type, log_snippet, pod_restarts, risk_score)

        # Add risk factors if run_id provided
        if run_id:
            run = PipelineRun.query.filter_by(run_id=run_id).first()
            if run:
                rca["risk_factors"] = analyze_risk_factors({
                    "risk_score": run.risk_score, "branch": run.branch,
                    "duration_secs": run.duration_secs, "triggered_by": run.triggered_by,
                })

        rca["run_id"] = run_id
        return jsonify(rca)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# SELF-HEALING API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/heal/<run_id>", methods=["POST"])
def api_heal(run_id):
    """Manually trigger healing for a specific run."""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.healing import scheduler
        context = request.json or {}
        result  = scheduler.trigger_now(run_id, context)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/healing/status")
def api_healing_status():
    """List recent healing events."""
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        events = HealingEvent.query.order_by(HealingEvent.created_at.desc()).limit(20).all()
        return jsonify({
            "events": [
                {"run_id": e.run_id, "failure_type": e.failure_type,
                 "strategy": e.strategy, "outcome": e.outcome,
                 "timestamp": e.timestamp}
                for e in events
            ],
            "total": HealingEvent.query.count(),
            "resolved": HealingEvent.query.filter_by(outcome="Resolved").count(),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# TEE API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/tee/status")
def tee_status():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from tee import secrets as tee_secrets
        return jsonify(tee_secrets.get_tee_summary())
    except Exception as exc:
        return jsonify({"error": str(exc), "overall_status": "Error"}), 500


@main_bp.route("/api/tee/attestation")
def tee_attestation():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from tee import attestation
        nonce  = request.args.get("nonce", None)
        report = attestation.generate_attestation_report(nonce)
        return jsonify(report)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/tee/seal", methods=["POST"])
def tee_seal():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data  = request.json or {}
        key   = data.get("key", "")
        value = data.get("value", "")
        if not key or not value:
            return jsonify({"error": "key and value required"}), 400
        from tee import secure_storage
        ok = secure_storage.store_secret(key, value)
        return jsonify({"success": ok, "message": f"Secret '{key}' sealed."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/tee/secrets")
def tee_secrets_list():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from tee import secure_storage
        return jsonify(secure_storage.get_store_info())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# SECURITY API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/security/scan", methods=["POST"])
def security_scan():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data  = request.json or {}
        image = data.get("image", "cortex-api:latest")
        from security import scanner
        result = scanner.scan_image(image)
        # Notify if critical vulns found
        if result.get("critical", 0) > 0:
            try:
                from app.notifications import dispatcher
                dispatcher.notify("security", {
                    "image":    image,
                    "critical": result["critical"],
                    "high":     result["high"],
                })
            except Exception:
                pass
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/security/secrets")
def security_secrets_scan():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from security import secret_scanner
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return jsonify(secret_scanner.scan_directory(root))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# REPORTS API
# ═══════════════════════════════════════════════════════════════════

@main_bp.route("/api/reports/pipeline")
def report_pipeline():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import io
        runs_q  = PipelineRun.query.order_by(PipelineRun.created_at.desc()).limit(50).all()
        total   = PipelineRun.query.count()
        failed  = PipelineRun.query.filter_by(status="Failed").count()
        healed  = PipelineRun.query.filter_by(status="Healed").count()
        success = PipelineRun.query.filter_by(status="Success").count()
        stats   = {"total_runs": total, "failed": failed, "healed": healed,
                   "success_rate": round((success + healed) / total * 100, 1) if total else 0,
                   "active_alerts": Alert.query.filter_by(status="Active").count(),
                   "total_deps":    Deployment.query.count()}
        runs_data = [{"run_id": r.run_id, "branch": r.branch, "status": r.status,
                      "triggered_by": r.triggered_by, "duration_secs": r.duration_secs,
                      "risk_score": r.risk_score} for r in runs_q]

        from reports.generator import generate_pipeline_report
        data, mime = generate_pipeline_report(runs_data, stats)
        ext = "pdf" if "pdf" in mime else "json"
        return send_file(
            io.BytesIO(data), mimetype=mime,
            as_attachment=True,
            download_name=f"cortex_pipeline_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/reports/healing")
def report_healing():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import io
        events = HealingEvent.query.order_by(HealingEvent.created_at.desc()).limit(50).all()
        events_data = [{"run_id": e.run_id, "failure_type": e.failure_type,
                        "strategy": e.strategy, "outcome": e.outcome,
                        "created_at": str(e.created_at)} for e in events]

        from reports.generator import generate_healing_report
        data, mime = generate_healing_report(events_data)
        ext = "pdf" if "pdf" in mime else "json"
        return send_file(
            io.BytesIO(data), mimetype=mime,
            as_attachment=True,
            download_name=f"cortex_healing_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/api/reports/ai/<run_id>")
def report_ai(run_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import io
        run = PipelineRun.query.filter_by(run_id=run_id).first()
        if not run:
            return jsonify({"error": "Run not found"}), 404

        from ml.predict_failure import predict_failure_risk
        from ml.root_cause import analyze
        prediction = predict_failure_risk(run.repo, run.branch, 10, run.duration_secs)
        rca        = analyze(prediction.get("failure_type", ""), "", 0, run.risk_score)

        from reports.generator import generate_ai_report
        data, mime = generate_ai_report(run_id, prediction, rca)
        ext = "pdf" if "pdf" in mime else "json"
        return send_file(
            io.BytesIO(data), mimetype=mime,
            as_attachment=True,
            download_name=f"cortex_ai_report_{run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
