"""
Self-Healing Engine
~~~~~~~~~~~~~~~~~~~~
Orchestrates the healing workflow:
  Failure detected → AI predicts type → choose strategy → execute → verify → escalate
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class HealingEngine:
    """
    Core engine that drives the self-healing loop.
    Instantiate once per app and call handle_failure() for each detected failure.
    """

    def __init__(self, db, HealingEvent, PipelineRun):
        self.db           = db
        self.HealingEvent = HealingEvent
        self.PipelineRun  = PipelineRun

    def handle_failure(self, run_id: str, context: dict | None = None) -> dict:
        """
        Full healing cycle for a failed pipeline run.

        Parameters
        ----------
        run_id  : str  — e.g. "RUN-4816"
        context : dict — optional override for {pod_name, deployment_name, job_name, namespace}

        Returns
        -------
        dict — final healing result
        """
        context = context or {}
        context.setdefault("run_id", run_id)
        context.setdefault("namespace", "default")
        context.setdefault("deployment_name", "cortex-api")
        context.setdefault("pod_name", "cortex-api-pod")
        context.setdefault("job_name", "CortexCICD/Self-Healing-CI-CD")

        logger.info("[HealingEngine] Starting healing cycle for %s", run_id)

        # ── Step 1: Get failure type from DB or ML ────────────────
        run = self.PipelineRun.query.filter_by(run_id=run_id).first()
        failure_type = context.get("failure_type", "")
        if not failure_type and run:
            from ml.predict_failure import predict_failure_risk
            prediction = predict_failure_risk(
                repo=run.repo, branch=run.branch,
                files_changed=10, duration_secs=run.duration_secs,
            )
            failure_type = prediction.get("failure_type", "Unknown")
        context["failure_type"] = failure_type

        # ── Step 2: Choose strategy ───────────────────────────────
        from .strategies import choose_strategy, EscalateStrategy
        strategy = choose_strategy(failure_type)
        logger.info("[HealingEngine] Strategy chosen: %s", strategy.name)

        # ── Step 3: Execute strategy ──────────────────────────────
        result = strategy.execute(context)

        # ── Step 4: If primary failed, try escalation ─────────────
        if not result["success"]:
            logger.warning("[HealingEngine] Primary strategy failed — escalating.")
            escalate_result = EscalateStrategy().execute(context)
            result["escalated"] = True
            result["escalation"] = escalate_result
            outcome = "Escalated"
        else:
            outcome = "Resolved"

        # ── Step 5: Record healing event in DB ───────────────────
        try:
            event = self.HealingEvent(
                run_id=run_id,
                failure_type=failure_type or "Unknown",
                strategy=strategy.name,
                outcome=outcome,
                created_at=datetime.utcnow(),
            )
            self.db.session.add(event)

            # Update pipeline run status
            if run:
                run.status = "Healed" if outcome == "Resolved" else "Failed"
                self.db.session.add(run)

            self.db.session.commit()
            logger.info("[HealingEngine] Healing event recorded: %s → %s", run_id, outcome)
        except Exception as exc:
            logger.error("[HealingEngine] DB write error: %s", exc)

        result["run_id"]       = run_id
        result["failure_type"] = failure_type
        return result

    def get_pending_failures(self) -> list:
        """Return all pipeline runs with status 'Failed' that have no healing event."""
        try:
            healed_run_ids = {e.run_id for e in self.HealingEvent.query.all()}
            failed_runs = self.PipelineRun.query.filter_by(status="Failed").all()
            return [r for r in failed_runs if r.run_id not in healed_run_ids]
        except Exception as exc:
            logger.error("[HealingEngine] get_pending_failures error: %s", exc)
            return []
