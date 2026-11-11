"""
Health Endpoints
~~~~~~~~~~~~~~~~
Kubernetes-compatible health probes:

  GET /healthz  — Liveness:  app process is alive (always 200 if Flask is up)
  GET /readyz   — Readiness: DB reachable + healing scheduler running
  GET /livez    — Detailed:  per-component status with timestamps
"""

import logging
import os
from datetime import datetime, timezone
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)
logger    = logging.getLogger(__name__)

_start_time = datetime.now(timezone.utc)


# ── /healthz — Liveness ────────────────────────────────────────────

@health_bp.route("/healthz")
def healthz():
    """
    Kubernetes liveness probe.
    Returns 200 as long as the Flask process is alive.
    If this fails, Kubernetes will restart the pod.
    """
    return jsonify({
        "status":    "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


# ── /readyz — Readiness ────────────────────────────────────────────

@health_bp.route("/readyz")
def readyz():
    """
    Kubernetes readiness probe.
    Returns 200 only if the app is fully ready to serve traffic:
      • SQLite / DB is reachable
      • Healing scheduler is running
    Returns 503 if any critical dependency is down.
    """
    checks = {}
    all_ok = True

    # ── Check: Database ───────────────────────────────────────────
    try:
        from app.db import db
        db.session.execute(db.text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        all_ok = False

    # ── Check: Healing Scheduler ──────────────────────────────────
    try:
        from app.healing import scheduler as healing_scheduler
        running = healing_scheduler._scheduler is not None
        checks["healing_scheduler"] = {
            "status": "ok" if running else "degraded",
            "detail": "APScheduler running" if running else "using threading fallback",
        }
        # degraded is still ready — threading fallback works fine
    except Exception as exc:
        checks["healing_scheduler"] = {"status": "error", "detail": str(exc)}
        all_ok = False

    # ── Check: Status Poller ──────────────────────────────────────
    try:
        from app.services import status_poller
        running = status_poller.is_running()
        checks["status_poller"] = {
            "status": "ok" if running else "degraded",
            "detail": "running" if running else "not started",
        }
    except Exception as exc:
        checks["status_poller"] = {"status": "error", "detail": str(exc)}

    http_status = 200 if all_ok else 503
    return jsonify({
        "status":    "ok" if all_ok else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks":    checks,
    }), http_status


# ── /livez — Detailed Component Status ────────────────────────────

@health_bp.route("/livez")
def livez():
    """
    Detailed liveness report.
    Not used by Kubernetes directly but useful for ops dashboards.
    Returns per-component status: DB, scheduler, ML model, healing engine.
    """
    components = {}
    uptime_secs = int((datetime.now(timezone.utc) - _start_time).total_seconds())

    # ── Database ──────────────────────────────────────────────────
    try:
        from app.db import db
        from app.models import PipelineRun, HealingEvent, Alert
        db.session.execute(db.text("SELECT 1"))
        components["database"] = {
            "status":        "ok",
            "pipeline_runs": PipelineRun.query.count(),
            "healing_events": HealingEvent.query.count(),
            "active_alerts": Alert.query.filter_by(status="Active").count(),
        }
    except Exception as exc:
        logger.warning("[Livez] DB check failed: %s", exc)
        components["database"] = {"status": "error", "detail": "database unavailable"}

    # ── Healing Scheduler ─────────────────────────────────────────
    try:
        from app.healing import scheduler as hs
        sched_running = hs._scheduler is not None
        components["healing_scheduler"] = {
            "status": "ok" if sched_running else "degraded",
            "backend": "APScheduler" if sched_running else "threading fallback",
            "engine_ready": hs._engine is not None,
        }
    except Exception as exc:
        logger.warning("[Livez] Scheduler check failed: %s", exc)
        components["healing_scheduler"] = {"status": "error", "detail": "scheduler unavailable"}

    # ── Status Poller ─────────────────────────────────────────────
    try:
        from app.services import status_poller
        components["status_poller"] = {
            "status":   "ok" if status_poller.is_running() else "stopped",
            "interval": f"{status_poller.POLL_INTERVAL}s",
        }
    except Exception as exc:
        logger.warning("[Livez] StatusPoller check failed: %s", exc)
        components["status_poller"] = {"status": "error", "detail": "poller unavailable"}

    # ── ML Model ──────────────────────────────────────────────────
    try:
        from ml.predict_failure import _model, _type_model
        components["ml_model"] = {
            "status":      "ok" if _model is not None else "not_loaded",
            "risk_model":  type(_model).__name__ if _model else None,
            "type_model":  type(_type_model).__name__ if _type_model else None,
        }
    except Exception as exc:
        logger.warning("[Livez] ML model check failed: %s", exc)
        components["ml_model"] = {"status": "error", "detail": "model unavailable"}

    # ── Jenkins Integration ───────────────────────────────────────
    try:
        from app.integrations import jenkins_client as jc
        client_ready = jc._jenkins_instance is not None
        components["jenkins"] = {
            "status":     "connected" if client_ready else "mock_mode",
            "configured": bool(os.getenv("JENKINS_URL")),
        }
    except Exception as exc:
        logger.warning("[Livez] Jenkins check failed: %s", exc)
        components["jenkins"] = {"status": "error", "detail": "jenkins check unavailable"}

    overall = all(
        c.get("status") in ("ok", "connected", "mock_mode", "degraded")
        for c in components.values()
    )

    return jsonify({
        "status":       "ok" if overall else "degraded",
        "uptime_secs":  uptime_secs,
        "started_at":   _start_time.isoformat(),
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "components":   components,
    }), 200
