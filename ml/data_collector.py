"""
Real training data collector.
Extracts labelled feature vectors from completed PipelineRun + HealingEvent records.
Called by worker.py after each run reaches terminal status.
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def collect_training_sample(run, healing=None) -> dict | None:
    """
    Extract one labelled training sample from a PipelineRun (and optional HealingEvent).
    Returns None if the run is not in a terminal state.
    """
    if run.status not in ("Failed", "Healed", "Success"):
        return None
    return {
        "files_changed":        run.files_changed or 0,
        "duration_secs":        run.duration_secs or 0,
        "hour_of_day":          run.created_at.hour,
        "day_of_week":          run.created_at.weekday(),
        "branch_is_main":       int(run.branch in ("main", "master")),
        "risk_score":           run.risk_score or 0,
        "failed":               int(run.status == "Failed"),
        "failure_type":         healing.failure_type if healing else "None",
    }


def get_all_training_samples(app_context) -> list[dict]:
    """Collect all labelled samples from the database.

    Must be called inside a Flask application context. If called outside one,
    returns an empty list silently so the ML model falls back to synthetic data.
    """
    samples = []
    try:
        from flask import current_app  # noqa: F401 — triggers RuntimeError if no ctx
        _ = current_app._get_current_object()
    except RuntimeError:
        # No active app context — skip DB collection, use synthetic data instead
        logger.debug("[DataCollector] No app context available — skipping DB sample collection.")
        return samples
    try:
        from app.models import PipelineRun, HealingEvent
        runs = PipelineRun.query.filter(
            PipelineRun.status.in_(["Failed", "Healed", "Success"])
        ).all()
        healed_map = {h.run_id: h for h in HealingEvent.query.all()}
        for run in runs:
            s = collect_training_sample(run, healed_map.get(run.run_id))
            if s:
                samples.append(s)
    except Exception as exc:
        logger.error("[DataCollector] Error: %s", exc)
    return samples
