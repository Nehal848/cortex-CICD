"""
Self-Healing Strategies
~~~~~~~~~~~~~~~~~~~~~~~~
Each strategy class implements a single healing action.
Strategies are chosen by the HealingEngine based on the predicted failure type.
"""

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseStrategy:
    name        = "Base"
    description = "Base healing strategy"

    def execute(self, context: dict) -> dict:
        """
        Execute the strategy.

        Parameters
        ----------
        context : dict
            Keys: run_id, failure_type, pod_name, deployment_name, job_name,
                  build_number, namespace, log_snippet

        Returns
        -------
        dict
            {success, outcome, message, actions_taken, duration_ms}
        """
        raise NotImplementedError

    def _result(self, success: bool, message: str, actions: list[str], t0: float) -> dict:
        elapsed_ms = round((time.time() - t0) * 1000)
        return {
            "success":       success,
            "outcome":       "Resolved" if success else "Failed",
            "strategy":      self.name,
            "message":       message,
            "actions_taken": actions,
            "duration_ms":   elapsed_ms,
            "timestamp":     datetime.utcnow().isoformat(),
        }


# ── Concrete strategies ────────────────────────────────────────────

class AutoRetryStrategy(BaseStrategy):
    name        = "Auto Retry"
    description = "Re-trigger the failed pipeline build via Jenkins."

    def execute(self, context: dict) -> dict:
        t0 = time.time()
        actions = []
        job_name = context.get("job_name", "CortexCICD/Self-Healing-CI-CD")

        try:
            from ..integrations import jenkins_client
            result = jenkins_client.trigger_build(job_name)
            if result.get("success"):
                actions.append(f"Triggered new build for job '{job_name}'")
                actions.append("Waiting for build to register in Jenkins…")
                time.sleep(1)
                return self._result(True, f"Pipeline re-triggered successfully for '{job_name}'.", actions, t0)
            else:
                return self._result(False, f"Jenkins trigger failed: {result.get('message')}", actions, t0)
        except Exception as exc:
            logger.error("[AutoRetry] Error: %s", exc)
            actions.append(f"Error: {exc}")
            return self._result(False, str(exc), actions, t0)


class PodRestartStrategy(BaseStrategy):
    name        = "Pod Restart"
    description = "Delete the failing pod so Kubernetes recreates it."

    def execute(self, context: dict) -> dict:
        t0 = time.time()
        actions = []
        pod_name  = context.get("pod_name", "cortex-api-unknown")
        namespace = context.get("namespace", "default")

        try:
            from ..integrations import k8s_client
            actions.append(f"Identifying pod '{pod_name}' in namespace '{namespace}'")
            result = k8s_client.restart_pod(pod_name, namespace)
            if result.get("success"):
                actions.append(f"Pod '{pod_name}' deleted — Kubernetes will recreate it")
                actions.append("Waiting for pod health check…")
                time.sleep(2)
                # Verify pod is back
                pods = k8s_client.list_pods(namespace)
                dep_name = pod_name.rsplit("-", 2)[0]  # strip pod hash
                running = any(
                    p["name"].startswith(dep_name) and p["phase"] == "Running"
                    for p in pods
                )
                if running:
                    actions.append("Replacement pod is Running — health verified ✓")
                    return self._result(True, f"Pod '{pod_name}' restarted and healthy.", actions, t0)
                else:
                    return self._result(False, "Replacement pod did not reach Running state.", actions, t0)
            else:
                return self._result(False, result.get("message", "Unknown error"), actions, t0)
        except Exception as exc:
            logger.error("[PodRestart] Error: %s", exc)
            return self._result(False, str(exc), actions, t0)


class RollbackStrategy(BaseStrategy):
    name        = "Rollback"
    description = "Roll back the Kubernetes deployment to the previous revision."

    def execute(self, context: dict) -> dict:
        t0 = time.time()
        actions = []
        dep_name  = context.get("deployment_name", "cortex-api")
        namespace = context.get("namespace", "default")

        try:
            from ..integrations import k8s_client
            actions.append(f"Initiating rollback for deployment '{dep_name}'")
            result = k8s_client.rollback_deployment(dep_name, namespace)
            if result.get("success"):
                actions.append("Deployment rolled back to previous revision")
                actions.append("Verifying rollback health…")
                time.sleep(2)
                deployments = k8s_client.list_deployments(namespace)
                dep = next((d for d in deployments if d["name"] == dep_name), None)
                if dep and dep["ready"] >= 1:
                    actions.append(f"Deployment '{dep_name}' is healthy ({dep['ready']}/{dep['replicas']} ready) ✓")
                    return self._result(True, f"Deployment '{dep_name}' rolled back successfully.", actions, t0)
                else:
                    return self._result(False, "Deployment unhealthy after rollback.", actions, t0)
            else:
                return self._result(False, result.get("message", "Unknown error"), actions, t0)
        except Exception as exc:
            logger.error("[Rollback] Error: %s", exc)
            return self._result(False, str(exc), actions, t0)


class ScaleUpStrategy(BaseStrategy):
    name        = "Scale Up"
    description = "Increase the deployment replica count to absorb high load."

    def execute(self, context: dict) -> dict:
        t0 = time.time()
        actions = []
        dep_name  = context.get("deployment_name", "cortex-api")
        namespace = context.get("namespace", "default")

        try:
            from ..integrations import k8s_client
            # Get current replica count
            deployments = k8s_client.list_deployments(namespace)
            dep = next((d for d in deployments if d["name"] == dep_name), None)
            current = dep["replicas"] if dep else 1
            new_replicas = min(current + 1, 5)  # cap at 5

            actions.append(f"Current replicas: {current} — scaling to {new_replicas}")
            result = k8s_client.scale_deployment(dep_name, new_replicas, namespace)
            if result.get("success"):
                actions.append(f"Deployment '{dep_name}' scaled to {new_replicas} replicas")
                return self._result(True, f"Scaled '{dep_name}' from {current} → {new_replicas} replicas.", actions, t0)
            else:
                return self._result(False, result.get("message", "Unknown error"), actions, t0)
        except Exception as exc:
            logger.error("[ScaleUp] Error: %s", exc)
            return self._result(False, str(exc), actions, t0)


class EscalateStrategy(BaseStrategy):
    name        = "Escalate"
    description = "All automated strategies exhausted — notify on-call team."

    def execute(self, context: dict) -> dict:
        t0 = time.time()
        actions = []
        run_id = context.get("run_id", "UNKNOWN")

        try:
            from ..notifications import dispatcher
            msg = (
                f"🚨 *CortexCICD Alert* — Pipeline `{run_id}` failed.\n"
                f"All automated healing strategies were exhausted.\n"
                f"Failure type: `{context.get('failure_type', 'Unknown')}`\n"
                f"Manual investigation required."
            )
            dispatcher.notify("escalation", {
                "run_id":       run_id,
                "failure_type": context.get("failure_type"),
                "message":      msg,
            })
            actions.append("Escalation notification sent to Slack/Email")
        except Exception as exc:
            logger.warning("[Escalate] Notification failed: %s", exc)
            actions.append(f"Notification failed: {exc}")

        return self._result(
            success=False,
            message=f"Escalated pipeline {run_id} to on-call team. Manual intervention required.",
            actions=actions,
            t0=t0,
        )


# ── Strategy selector ──────────────────────────────────────────────

_STRATEGY_MAP = {
    "Test Suite Timeout":   AutoRetryStrategy,
    "Network Timeout":      AutoRetryStrategy,
    "OOM — Pod Evicted":    PodRestartStrategy,
    "Liveness Probe Fail":  PodRestartStrategy,
    "CrashLoopBackOff":     PodRestartStrategy,
    "Build Script Error":   RollbackStrategy,
    "Dependency Resolution":RollbackStrategy,
    "High CPU Saturation":  ScaleUpStrategy,
    "Deploy Failure":       RollbackStrategy,
    "Image Pull Error":     RollbackStrategy,
}


def choose_strategy(failure_type: str) -> BaseStrategy:
    """Select the most appropriate strategy for a given failure type."""
    cls = _STRATEGY_MAP.get(failure_type, RollbackStrategy)
    return cls()


def all_strategies() -> list[str]:
    return [AutoRetryStrategy.name, PodRestartStrategy.name,
            RollbackStrategy.name, ScaleUpStrategy.name, EscalateStrategy.name]
