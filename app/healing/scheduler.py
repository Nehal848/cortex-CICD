"""
Healing Scheduler
~~~~~~~~~~~~~~~~~
Background thread (APScheduler) that polls for Failed pipeline runs
every 30 seconds and triggers the HealingEngine automatically.
"""

import logging
import threading

logger = logging.getLogger(__name__)

_scheduler = None
_engine    = None


def start(app, db, HealingEvent, PipelineRun):
    """
    Start the background healing scheduler.
    Safe to call multiple times — idempotent.
    """
    global _scheduler, _engine

    if _scheduler is not None:
        return  # already running

    from .engine import HealingEngine
    _engine = HealingEngine(db, HealingEvent, PipelineRun)

    def _poll():
        """Poll for failed runs and attempt healing inside the app context."""
        with app.app_context():
            try:
                pending = _engine.get_pending_failures()
                if pending:
                    logger.info("[Scheduler] Found %d unhealed failure(s).", len(pending))
                    for run in pending:
                        logger.info("[Scheduler] Auto-healing run: %s", run.run_id)
                        _engine.handle_failure(run.run_id)
            except Exception as exc:
                logger.error("[Scheduler] Poll error: %s", exc)

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(_poll, "interval", seconds=30, id="healing_poll", max_instances=1)
        _scheduler.start()
        logger.info("[Scheduler] Healing scheduler started (30s interval).")
    except ImportError:
        # APScheduler not installed — use a simple threading fallback
        logger.warning("[Scheduler] APScheduler not found — using threading fallback (60s interval).")
        _thread_scheduler(app, _poll)


def _thread_scheduler(app, poll_fn, interval: int = 60):
    """Fallback scheduler using Python threading."""
    import time

    def loop():
        while True:
            time.sleep(interval)
            poll_fn()

    t = threading.Thread(target=loop, daemon=True, name="HealingScheduler")
    t.start()


def stop():
    global _scheduler
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
        logger.info("[Scheduler] Healing scheduler stopped.")


def trigger_now(run_id: str, context: dict | None = None) -> dict:
    """Manually trigger healing for a specific run (called from API)."""
    if _engine is None:
        return {"success": False, "message": "Healing engine not initialised."}
    return _engine.handle_failure(run_id, context)
