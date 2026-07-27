"""
Status Poller
~~~~~~~~~~~~~
Background thread that periodically polls Jenkins for the status of
every PipelineRun stuck in "In Progress".

On completion:
  • SUCCESS  → status = "Success", duration_secs updated
  • FAILURE  → status = "Failed", healing engine triggered
  • ABORTED  → status = "Failed"
  • Still building → left as "In Progress", retried next cycle
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_app = None
_db = None

POLL_INTERVAL = 15  # seconds between full sweeps


def start(app, db):
    """Start the status poller background thread. Idempotent."""
    global _thread, _app, _db
    if _thread is not None and _thread.is_alive():
        return

    _app = app
    _db  = db
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="StatusPoller")
    _thread.start()
    logger.info("[StatusPoller] Started (interval=%ds).", POLL_INTERVAL)


def stop():
    """Signal the poller to stop gracefully."""
    _stop_event.set()
    logger.info("[StatusPoller] Stop requested.")


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


# ── Internal loop ──────────────────────────────────────────────────

def _loop():
    while not _stop_event.is_set():
        try:
            _poll_once()
        except Exception as exc:
            logger.error("[StatusPoller] Unexpected error: %s", exc)
        _stop_event.wait(POLL_INTERVAL)


def _poll_once():
    """Find all In Progress runs and try to resolve their Jenkins status."""
    with _app.app_context():
        from app.models import PipelineRun
        in_progress = PipelineRun.query.filter_by(status="In Progress").all()

        if not in_progress:
            return

        logger.info("[StatusPoller] Checking %d In Progress run(s).", len(in_progress))

        for run in in_progress:
            try:
                _resolve_run(run)
            except Exception as exc:
                logger.error("[StatusPoller] Error resolving %s: %s", run.run_id, exc)


def _resolve_run(run):
    """
    Poll Jenkins for a single run.  If no jenkins_build_number is stored,
    we try to infer it from the latest build of the job.
    """
    from app.integrations import jenkins_client as jc
    from app.models import PipelineRun
    from app.healing import scheduler as healing_scheduler

    job_name     = run.jenkins_job_name or "CortexCICD/Self-Healing-CI-CD"
    build_number = run.jenkins_build_number

    # If we don't have a build number, attempt to grab the latest build
    if not build_number:
        jobs = jc.get_all_jobs()
        matched = next((j for j in jobs if j["name"] == job_name), None)
        if matched and matched.get("last_build_number"):
            build_number = matched["last_build_number"]
            run.jenkins_build_number = build_number
        else:
            # Can't determine build number yet — check again next cycle
            logger.debug("[StatusPoller] No build number for %s, skipping.", run.run_id)
            return

    status_info = jc.get_build_status(job_name, build_number)

    # Still building — nothing to do yet
    if status_info.get("building", False):
        logger.debug("[StatusPoller] %s still building (build #%s).", run.run_id, build_number)
        return

    jenkins_result = status_info.get("result", "UNKNOWN")
    duration_ms    = status_info.get("duration_ms", 0)

    if jenkins_result == "SUCCESS":
        run.status        = "Success"
        run.duration_secs = max(1, duration_ms // 1000)
        logger.info("[StatusPoller] %s → Success (build #%s, %ds).",
                    run.run_id, build_number, run.duration_secs)

    elif jenkins_result in ("FAILURE", "ABORTED", "UNSTABLE"):
        run.status = "Failed"
        run.duration_secs = max(1, duration_ms // 1000)
        logger.info("[StatusPoller] %s → Failed (build #%s, result=%s).",
                    run.run_id, build_number, jenkins_result)

        # Kick off self-healing automatically
        try:
            healing_scheduler.trigger_now(run.run_id)
        except Exception as exc:
            logger.warning("[StatusPoller] Could not trigger healing for %s: %s",
                           run.run_id, exc)
    else:
        # UNKNOWN / null — Jenkins may not have started the build yet
        logger.debug("[StatusPoller] %s result=%s — waiting.", run.run_id, jenkins_result)
        return

    # Persist the status change
    _db.session.add(run)
    _db.session.commit()

    # SSE: pipeline updated
    try:
        from app.events import publish
        publish("pipeline.updated", {
            "run_id": run.run_id,
            "status": run.status,
            "duration_secs": run.duration_secs,
        })
    except Exception:
        pass
