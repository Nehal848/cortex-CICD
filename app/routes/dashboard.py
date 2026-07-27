from flask import Blueprint, render_template, redirect, url_for, session
from app.models import PipelineRun, Deployment, HealingEvent, Alert

dashboard_bp = Blueprint('dashboard', __name__)

def _require_login():
    if not session.get("logged_in"):
        return redirect(url_for("auth.login"))
    return None

@dashboard_bp.route("/")
def index():
    return render_template("index.html")

@dashboard_bp.route("/docs")
def docs():
    return render_template("docs.html")

@dashboard_bp.route("/dashboard")
def dashboard():
    redir = _require_login()
    if redir: return redir

    runs        = PipelineRun.query.order_by(PipelineRun.created_at.desc()).limit(8).all()
    from app.services.pipeline_service import get_dashboard_stats
    stats       = get_dashboard_stats()

    return render_template("dashboard.html", active_page="dashboard", runs=runs, stats=stats)

@dashboard_bp.route("/pipeline")
def pipeline():
    redir = _require_login()
    if redir: return redir
    runs = PipelineRun.query.order_by(PipelineRun.created_at.desc()).all()
    return render_template("pipeline.html", active_page="pipeline", runs=runs)

@dashboard_bp.route("/deployments")
def deployments():
    redir = _require_login()
    if redir: return redir
    deps = Deployment.query.order_by(Deployment.created_at.desc()).all()
    return render_template("deployments.html", active_page="deployments", deployments=deps)

@dashboard_bp.route("/self-healing")
def self_healing():
    redir = _require_login()
    if redir: return redir
    events = HealingEvent.query.order_by(HealingEvent.created_at.desc()).all()
    return render_template("self_healing.html", active_page="self_healing", events=events)

@dashboard_bp.route("/kubernetes")
def kubernetes():
    redir = _require_login()
    if redir: return redir
    return render_template("kubernetes.html", active_page="kubernetes")

@dashboard_bp.route("/monitoring")
def monitoring():
    redir = _require_login()
    if redir: return redir
    return render_template("monitoring.html", active_page="monitoring")

@dashboard_bp.route("/logs")
def logs():
    redir = _require_login()
    if redir: return redir
    runs = PipelineRun.query.order_by(PipelineRun.created_at.desc()).limit(20).all()
    return render_template("logs.html", active_page="logs", runs=runs)

@dashboard_bp.route("/prediction")
def prediction():
    redir = _require_login()
    if redir: return redir
    runs = PipelineRun.query.order_by(PipelineRun.risk_score.desc()).limit(10).all()
    return render_template("prediction.html", active_page="prediction", runs=runs)

@dashboard_bp.route("/alerts")
def alerts():
    redir = _require_login()
    if redir: return redir
    all_alerts = Alert.query.order_by(Alert.created_at.desc()).all()
    return render_template("alerts.html", active_page="alerts", alerts=all_alerts)

@dashboard_bp.route("/settings")
def settings():
    redir = _require_login()
    if redir: return redir
    return render_template("settings.html", active_page="settings")

@dashboard_bp.route("/tee")
def tee():
    redir = _require_login()
    if redir: return redir
    return render_template("tee.html", active_page="tee")
