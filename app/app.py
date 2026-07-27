import os
import sys
from datetime import datetime, timedelta
from flask import Flask

# ── Add project root to path so tee/, ml/, security/, reports/ are importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .db import db
from .models import PipelineRun, Deployment, HealingEvent, Alert


def create_app(test_config: dict | None = None):
    # ── Load .env ─────────────────────────────────────────────────
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
    except ImportError:
        pass

    app = Flask(__name__)
    from .config import Config
    app.config.from_object(Config)

    # Use SECRET_KEY from env, fall back to random
    app.secret_key = app.config.get("SECRET_KEY", os.urandom(24).hex())

    # ── Database config ────────────────────────────────────────────
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + os.path.join(basedir, "cortex.db")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Allow test_config to override (e.g., in-memory SQLite for tests)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    # ── Register blueprints ─────────────────────────────────────────
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.api import api_bp
    from .routes.webhooks import webhooks_bp
    from .routes.health import health_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(health_bp)

    # ── Create tables & seed on first run ─────────────────────────
    with app.app_context():
        db.create_all()
        _migrate_schema()   # Option B: safe ALTER TABLE for new columns
        if not test_config:
            _seed_if_empty()

    # ── Boot TEE enclave & migrate secrets ────────────────────────
    try:
        from app.tee import secrets as tee_secrets
        tee_secrets.bootstrap()
    except Exception as exc:
        app.logger.warning("[TEE] Could not initialise TEE: %s", exc)

    # ── Start self-healing background scheduler ───────────────────
    try:
        from .healing import scheduler
        scheduler.start(app, db, HealingEvent, PipelineRun)
    except Exception as exc:
        app.logger.warning("[Healing] Scheduler start failed: %s", exc)

    # ── Start pipeline status poller ──────────────────────────────
    try:
        from .services import status_poller
        status_poller.start(app, db)
    except Exception as exc:
        app.logger.warning("[StatusPoller] Start failed: %s", exc)

    # ── Train ML model in the background (non-blocking) ───────────
    # ── Train ML model in the background (non-blocking) ───────────
    try:
        import threading
        def _train_ml():
            try:
                from ml.predict_failure import _load_or_train
                _load_or_train()
            except Exception:
                pass
        threading.Thread(target=_train_ml, daemon=True, name="MLTrainer").start()
    except Exception:
        pass

    # ── Start SSE metrics ticker (metrics.tick every 30s, heartbeat every 60s) ─
    if not test_config:  # skip background threads during tests
        try:
            import threading as _t
            def _sse_ticker():
                import time
                from app.events import publish
                from app.integrations import prometheus_client as pc
                tick = 0
                while True:
                    time.sleep(30)
                    tick += 1
                    try:
                        publish("metrics.tick", {
                            "cpu_percent":    pc.get_cpu_usage(),
                            "memory_percent": pc.get_memory_usage(),
                            "disk_percent":   pc.get_disk_usage(),
                            "source":         "prometheus" if pc._is_available() else "simulated",
                        })
                    except Exception:
                        pass
                    if tick % 2 == 0:  # every 60s
                        try:
                            from app.events import subscriber_count
                            from app.services.status_poller import is_running
                            publish("system.status", {
                                "sse_clients":     subscriber_count(),
                                "poller_running":  is_running(),
                            })
                        except Exception:
                            pass
            _t.Thread(target=_sse_ticker, daemon=True, name="SSETicker").start()
        except Exception as exc:
            app.logger.warning("[SSE] Ticker start failed: %s", exc)

    return app


# ── Schema Migration Helper (Option B) ────────────────────────────

def _migrate_schema():
    """
    Safely add new columns to existing tables using raw SQLite ALTER TABLE.
    SQLAlchemy's db.create_all() does not add columns to existing tables,
    so we handle it manually here.  Each ALTER is wrapped in its own
    try/except so a second startup is a no-op.
    """
    engine = db.engine
    with engine.connect() as conn:
        migrations = [
            # PipelineRun — Jenkins tracking columns (v1.1)
            "ALTER TABLE pipeline_runs ADD COLUMN jenkins_build_number INTEGER",
            "ALTER TABLE pipeline_runs ADD COLUMN jenkins_job_name VARCHAR(120)",
            # Alert — lifecycle tracking columns (v1.2)
            "ALTER TABLE alerts ADD COLUMN acknowledged_by VARCHAR(60)",
            "ALTER TABLE alerts ADD COLUMN acknowledged_at DATETIME",
            "ALTER TABLE alerts ADD COLUMN resolved_by VARCHAR(60)",
            "ALTER TABLE alerts ADD COLUMN resolved_at DATETIME",
            "ALTER TABLE alerts ADD COLUMN silenced_until DATETIME",
        ]
        for sql in migrations:
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print(f"[Cortex] Migration applied: {sql[:60]}…")
            except Exception:
                # Column already exists — expected on any run after the first
                pass


# ── DB Seed ────────────────────────────────────────────────────────

def _seed_if_empty():
    """Populate the DB with realistic sample data if tables are empty."""
    if PipelineRun.query.count() > 0:
        return  # already seeded

    now = datetime.utcnow()

    # ── Pipeline Runs ──────────────────────────────────────────────
    runs = [
        PipelineRun(run_id="RUN-4819", repo="CortexCICD/Self-Healing-CI-CD", branch="main",
                    status="Success",     triggered_by="GitPush",   duration_secs=142, risk_score=12,
                    created_at=now - timedelta(minutes=10)),
        PipelineRun(run_id="RUN-4818", repo="CortexCICD/Self-Healing-CI-CD", branch="main",
                    status="Healed",      triggered_by="GitPush",   duration_secs=310, risk_score=78,
                    created_at=now - timedelta(hours=1)),
        PipelineRun(run_id="RUN-4817", repo="CortexCICD/Self-Healing-CI-CD", branch="feature/ui-update",
                    status="Success",     triggered_by="Manual",    duration_secs=98,  risk_score=8,
                    created_at=now - timedelta(hours=3)),
        PipelineRun(run_id="RUN-4816", repo="CortexCICD/Self-Healing-CI-CD", branch="main",
                    status="Failed",      triggered_by="GitPush",   duration_secs=55,  risk_score=91,
                    created_at=now - timedelta(hours=5)),
        PipelineRun(run_id="RUN-4815", repo="CortexCICD/Self-Healing-CI-CD", branch="hotfix/auth",
                    status="Success",     triggered_by="Manual",    duration_secs=120, risk_score=22,
                    created_at=now - timedelta(hours=8)),
        PipelineRun(run_id="RUN-4814", repo="CortexCICD/Self-Healing-CI-CD", branch="main",
                    status="Healed",      triggered_by="Scheduled", duration_secs=270, risk_score=65,
                    created_at=now - timedelta(hours=12)),
        PipelineRun(run_id="RUN-4813", repo="CortexCICD/Self-Healing-CI-CD", branch="develop",
                    status="Success",     triggered_by="GitPush",   duration_secs=105, risk_score=15,
                    created_at=now - timedelta(days=1)),
        PipelineRun(run_id="RUN-4812", repo="CortexCICD/Self-Healing-CI-CD", branch="main",
                    status="Failed",      triggered_by="GitPush",   duration_secs=40,  risk_score=88,
                    created_at=now - timedelta(days=1, hours=4)),
    ]

    # ── Deployments ────────────────────────────────────────────────
    deployments = [
        Deployment(name="cortex-api",       environment="Production", version="v2.4.1",
                   status="Running",  deployed_by="CI/CD Auto",  created_at=now - timedelta(minutes=15)),
        Deployment(name="cortex-ui",        environment="Production", version="v2.4.1",
                   status="Running",  deployed_by="CI/CD Auto",  created_at=now - timedelta(minutes=18)),
        Deployment(name="healing-agent",    environment="Production", version="v1.0.4",
                   status="Running",  deployed_by="CI/CD Auto",  created_at=now - timedelta(hours=2)),
        Deployment(name="ml-predictor",     environment="Staging",    version="v0.9.2",
                   status="Running",  deployed_by="admin",        created_at=now - timedelta(hours=5)),
        Deployment(name="prometheus-expt",  environment="Production", version="v2.46.0",
                   status="Running",  deployed_by="CI/CD Auto",  created_at=now - timedelta(hours=7)),
        Deployment(name="cortex-worker",    environment="Dev",        version="v2.5.0-rc1",
                   status="Stopped",  deployed_by="admin",        created_at=now - timedelta(days=1)),
        Deployment(name="redis-cache",      environment="Production", version="v7.2.4",
                   status="Running",  deployed_by="CI/CD Auto",  created_at=now - timedelta(days=2)),
        Deployment(name="postgres-main",    environment="Production", version="v16.3",
                   status="Running",  deployed_by="CI/CD Auto",  created_at=now - timedelta(days=3)),
    ]

    # ── Healing Events ─────────────────────────────────────────────
    healing_events = [
        HealingEvent(run_id="RUN-4818", failure_type="Test Suite Timeout",
                     strategy="Auto Retry",   outcome="Resolved",  created_at=now - timedelta(hours=1, minutes=5)),
        HealingEvent(run_id="RUN-4814", failure_type="OOM — Pod Evicted",
                     strategy="Pod Restart",  outcome="Resolved",  created_at=now - timedelta(hours=12, minutes=3)),
        HealingEvent(run_id="RUN-4816", failure_type="Dependency Resolution",
                     strategy="Rollback",     outcome="Escalated", created_at=now - timedelta(hours=5, minutes=10)),
        HealingEvent(run_id="RUN-4812", failure_type="Build Script Error",
                     strategy="Auto Retry",   outcome="Failed",    created_at=now - timedelta(days=1, hours=4)),
        HealingEvent(run_id="RUN-4810", failure_type="High CPU Saturation",
                     strategy="Scale Up",     outcome="Resolved",  created_at=now - timedelta(days=2)),
        HealingEvent(run_id="RUN-4807", failure_type="Network Timeout",
                     strategy="Traffic Reroute", outcome="Resolved", created_at=now - timedelta(days=3)),
        HealingEvent(run_id="RUN-4804", failure_type="Liveness Probe Fail",
                     strategy="Pod Restart",  outcome="Resolved",  created_at=now - timedelta(days=4)),
    ]

    # ── Alerts ─────────────────────────────────────────────────────
    alerts = [
        Alert(title="High Memory Usage on cortex-api pod",
              severity="High",     source="Prometheus", status="Active",   created_at=now - timedelta(minutes=22)),
        Alert(title="Pipeline RUN-4816 failed after 3 retries",
              severity="Critical", source="CI Engine",  status="Active",   created_at=now - timedelta(hours=5)),
        Alert(title="Staging deployment ml-predictor is degraded",
              severity="Medium",   source="K8s Monitor", status="Active",  created_at=now - timedelta(hours=6)),
        Alert(title="CPU spike detected on node cortex-worker-02",
              severity="Medium",   source="Prometheus", status="Resolved", created_at=now - timedelta(hours=9)),
        Alert(title="SSL certificate expires in 14 days",
              severity="Low",      source="Cert Manager", status="Active", created_at=now - timedelta(hours=11)),
        Alert(title="Disk usage on PV postgres-main at 82%",
              severity="High",     source="K8s Monitor", status="Active",  created_at=now - timedelta(days=1)),
        Alert(title="RUN-4814 auto-healed via Pod Restart",
              severity="Low",      source="Healing Agent", status="Resolved", created_at=now - timedelta(hours=12)),
    ]

    db.session.add_all(runs + deployments + healing_events + alerts)
    db.session.commit()
    print("[Cortex] Database seeded with sample data.")


# Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)