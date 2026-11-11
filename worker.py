"""
Dedicated background worker process for CortexCICD.

Runs autonomous self-healing cycles (HealingScheduler), Jenkins build
status polling (StatusPoller), and periodic telemetry SSE broadcasts over
Redis Pub/Sub when running in multi-container deployments (Docker/K8s).
"""

from __future__ import annotations

from datetime import datetime
import logging
import os
import signal
import sys
import threading

from app.app import create_app
from app.db import db
from app.events import publish, subscriber_count
from app.healing import scheduler
from app.integrations import prometheus_client as pc
from app.models import Alert, HealingEvent, PipelineRun, PlatformSetting
from app.services import status_poller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cortex.worker")


def _start_metrics_server() -> None:
    """Expose Prometheus metrics endpoint for the background worker."""
    try:
        port = int(os.getenv("WORKER_METRICS_PORT", "9101"))
    except ValueError:
        port = 9101
    if port <= 0:
        return
    try:
        from prometheus_client import start_http_server
        start_http_server(port)
        logger.info("[Worker] Prometheus metrics server listening on :%d", port)
    except Exception as exc:
        logger.warning("[Worker] Could not start metrics server on :%d: %s", port, exc)


def _check_resource_thresholds(app, cpu_val: float, mem_val: float) -> list[str]:
    """Create deduplicated Active alerts when CPU or memory exceeds configured thresholds."""
    created_titles = []
    with app.app_context():
        try:
            cpu_thresh = float(PlatformSetting.get_value("cpu_threshold", "85"))
        except (TypeError, ValueError):
            cpu_thresh = 85.0
        try:
            mem_thresh = float(PlatformSetting.get_value("memory_threshold", "80"))
        except (TypeError, ValueError):
            mem_thresh = 80.0
        checks = [
            (cpu_val, cpu_thresh, f"High CPU Usage ({cpu_val:.1f}% >= {cpu_thresh:.0f}%)", "High"),
            (mem_val, mem_thresh, f"High Memory Usage ({mem_val:.1f}% >= {mem_thresh:.0f}%)", "High"),
        ]
        for current, limit, title, severity in checks:
            if current < limit:
                continue
            metric_prefix = title.split("(", 1)[0].strip()
            existing = Alert.query.filter(
                Alert.status == "Active",
                Alert.source == "Prometheus",
                Alert.title.like(f"{metric_prefix}%"),
            ).first()
            if existing is not None:
                continue
            alert = Alert(
                title=title,
                severity=severity,
                source="Prometheus",
                status="Active",
                created_at=datetime.utcnow(),
            )
            db.session.add(alert)
            db.session.commit()
            created_titles.append(title)
            publish("alert.created", {
                "title": alert.title,
                "severity": alert.severity,
                "source": alert.source,
                "status": alert.status,
            })
    return created_titles


def main(run_once: bool = False) -> None:
    """Boot Flask app context and start worker loops cleanly."""
    app = create_app(enable_background=False)
    scheduler.start(app, db, HealingEvent, PipelineRun)
    status_poller.start(app, db)
    logger.info("[Worker] Cortex worker started (scheduler + status poller active).")

    if run_once:
        return

    _start_metrics_server()
    stop_event = threading.Event()

    def _handle_signal(signum, _frame):
        logger.info("[Worker] Received signal %s — shutting down gracefully.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not stop_event.wait(timeout=30):
        try:
            cpu_val = pc.get_cpu_usage()
            mem_val = pc.get_memory_usage()
            disk_val = pc.get_disk_usage()
            publish("metrics.tick", {
                "cpu_percent": cpu_val,
                "memory_percent": mem_val,
                "disk_percent": disk_val,
                "source": "prometheus" if pc._is_available() else "simulated",
            })
            _check_resource_thresholds(app, cpu_val, mem_val)
            publish("system.status", {
                "sse_clients": subscriber_count(),
                "poller_running": status_poller.is_running(),
            })
        except Exception as exc:
            logger.debug("[Worker] Tick broadcast warning: %s", exc)

    logger.info("[Worker] Cortex worker stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()

