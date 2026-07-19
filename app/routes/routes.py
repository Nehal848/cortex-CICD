from datetime import datetime
from flask import render_template, request, jsonify, redirect, url_for, session
from . import main_bp
from ..db import db
from ..models import PipelineRun, Deployment, HealingEvent, Alert


# ── Auth helper ───────────────────────────────────────────────────
def _require_login():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))
    return None


# ── Public routes ─────────────────────────────────────────────────
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


# ── Protected routes ──────────────────────────────────────────────
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

    success_rate = round((success + healed) / total_runs * 100, 1) if total_runs else 0

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


@main_bp.route("/docs")
def docs():
    # Public route — accessible from the landing page without login
    return render_template("docs.html")


@main_bp.route("/settings")
def settings():
    redir = _require_login()
    if redir: return redir
    return render_template("settings.html", active_page="settings")


# ── API endpoints ─────────────────────────────────────────────────
@main_bp.route("/api/pipeline/run", methods=["POST"])
def run_pipeline():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    # Determine next run ID
    last = PipelineRun.query.order_by(PipelineRun.id.desc()).first()
    if last:
        last_num = int(last.run_id.split("-")[1])
        new_run_id = f"RUN-{last_num + 1}"
    else:
        new_run_id = "RUN-4820"

    new_run = PipelineRun(
        run_id=new_run_id,
        repo="CortexCICD/Self-Healing-CI-CD",
        branch="main",
        status="In Progress",
        triggered_by="Manual",
        duration_secs=0,
        risk_score=0,
        created_at=datetime.utcnow(),
    )
    db.session.add(new_run)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Pipeline run triggered successfully.",
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

    total  = PipelineRun.query.count()
    failed = PipelineRun.query.filter_by(status="Failed").count()
    healed = PipelineRun.query.filter_by(status="Healed").count()
    success = PipelineRun.query.filter_by(status="Success").count()
    rate   = round((success + healed) / total * 100, 1) if total else 0

    return jsonify({
        "total_runs":    total,
        "failed_builds": failed,
        "healed_runs":   healed,
        "success_rate":  rate,
        "total_deps":    Deployment.query.count(),
        "active_alerts": Alert.query.filter_by(status="Active").count(),
    })
