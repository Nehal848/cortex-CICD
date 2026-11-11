"""
Webhook Receivers
~~~~~~~~~~~~~~~~~
Event-driven endpoints that replace polling-based integrations.

  POST /webhooks/github      — GitHub push / pull_request events
  POST /webhooks/jenkins     — Jenkins Generic Webhook Trigger build events
  POST /webhooks/prometheus  — Prometheus Alertmanager webhook payloads
"""

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")
logger      = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────

def _is_strict_webhook_mode() -> bool:
    return (
        current_app.config.get("ENV") == "production"
        or os.getenv("FLASK_ENV") == "production"
        or bool(current_app.config.get("STRICT_WEBHOOK_VERIFICATION", False))
    )


def _verify_shared_token(config_key: str, alt_header: str) -> bool:
    """
    Validate a shared webhook bearer/header secret using constant-time comparison.
    Fails closed when running in production / strict verification mode.
    """
    secret = current_app.config.get(config_key) or os.getenv(config_key, "")
    if not secret:
        if _is_strict_webhook_mode():
            logger.error("[Webhook] Production/strict mode active but %s not configured — failing closed.", config_key)
            return False
        return True

    auth_header = request.headers.get("Authorization", "")
    presented = ""
    if auth_header.lower().startswith("bearer "):
        presented = auth_header[7:].strip()
    if not presented:
        presented = request.headers.get(alt_header, "").strip()
    return bool(presented) and hmac.compare_digest(presented, secret)


def _verify_github_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """Validate the X-Hub-Signature-256 header from GitHub."""
    secret = current_app.config.get("GITHUB_WEBHOOK_SECRET") or os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        if _is_strict_webhook_mode():
            logger.error("[Webhook/GitHub] Production mode active but GITHUB_WEBHOOK_SECRET not configured — failing closed.")
            return False
        # Development / test mode fallback
        logger.warning("[Webhook/GitHub] GITHUB_WEBHOOK_SECRET not set — skipping HMAC check.")
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _jenkins_to_cortex_status(jenkins_result: str) -> str:
    """Map Jenkins build result to CortexCICD pipeline status."""
    mapping = {
        "SUCCESS":  "Success",
        "FAILURE":  "Failed",
        "ABORTED":  "Failed",
        "UNSTABLE": "Failed",
    }
    return mapping.get(jenkins_result.upper(), "Failed")


# ── GitHub Webhook ─────────────────────────────────────────────────

@webhooks_bp.route("/github", methods=["POST"])
def github_webhook():
    """
    Receives GitHub push and pull_request events.
    Validates HMAC-SHA256 signature, then triggers a CI pipeline.

    Expected headers:
      X-GitHub-Event: push | pull_request
      X-Hub-Signature-256: sha256=<hex>
    """
    payload_bytes = request.get_data()
    signature     = request.headers.get("X-Hub-Signature-256")

    if not _verify_github_signature(payload_bytes, signature):
        logger.warning("[Webhook/GitHub] Invalid signature — rejected.")
        return jsonify({"error": "Invalid signature"}), 401

    event = request.headers.get("X-GitHub-Event", "unknown")
    data  = request.get_json(silent=True) or {}

    # Only act on push to non-gh-pages branches, or PR open/sync
    if event == "push":
        ref    = data.get("ref", "")
        branch = ref.replace("refs/heads/", "")
        repo   = data.get("repository", {}).get("full_name", "unknown/unknown")
        pusher = data.get("pusher", {}).get("name", "GitHub")

        if not branch or branch == "gh-pages":
            return jsonify({"status": "skipped", "reason": "non-code branch"}), 200

        changed_files = set()
        for commit in data.get("commits") or []:
            if isinstance(commit, dict):
                changed_files.update(commit.get("added") or [])
                changed_files.update(commit.get("modified") or [])
                changed_files.update(commit.get("removed") or [])
        files_changed = len(changed_files) if changed_files else 10
        head_commit = data.get("head_commit") or {}
        commit_msg = (head_commit.get("message") or "").splitlines()[0][:250] if isinstance(head_commit, dict) and head_commit.get("message") else None

        logger.info(
            "[Webhook/GitHub] Push to %s/%s by %s (files=%d)",
            repo, branch, pusher, files_changed,
        )
        return _trigger_from_webhook(
            repo, branch, triggered_by="GitPush",
            files_changed=files_changed, commit_message=commit_msg,
        )

    elif event == "pull_request":
        action = data.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            return jsonify({"status": "skipped", "reason": f"action={action}"}), 200

        pr     = data.get("pull_request", {})
        branch = pr.get("head", {}).get("ref", "unknown")
        repo   = data.get("repository", {}).get("full_name", "unknown/unknown")
        pr_files = int(pr.get("changed_files") or 10)
        pr_title = str(pr.get("title") or "")[:250] or None

        logger.info("[Webhook/GitHub] PR %s on %s/%s (files=%d)", action, repo, branch, pr_files)
        return _trigger_from_webhook(
            repo, branch, triggered_by="PullRequest",
            files_changed=pr_files, commit_message=pr_title,
        )

    elif event == "ping":
        return jsonify({"status": "pong"}), 200

    return jsonify({"status": "ignored", "event": event}), 200


def _trigger_from_webhook(
    repo: str,
    branch: str,
    triggered_by: str,
    files_changed: int = 10,
    commit_message: str | None = None,
):
    """Create a PipelineRun record and trigger Jenkins build."""
    try:
        from app.services.pipeline_service import trigger_pipeline
        result = trigger_pipeline(
            repo,
            branch,
            triggered_by=triggered_by,
            files_changed=files_changed,
            commit_message=commit_message,
        )
        run = result["run"]
        return jsonify({
            "status":  "triggered",
            "run_id":  run.run_id,
            "branch":  run.branch,
            "mock":    result.get("mock", False),
        }), 201
    except Exception as exc:
        logger.error("[Webhook/GitHub] trigger_pipeline error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Jenkins Webhook ────────────────────────────────────────────────

@webhooks_bp.route("/jenkins", methods=["POST"])
def jenkins_webhook():
    """
    Receives build-completed events from the Jenkins
    Generic Webhook Trigger plugin.
    Requires JENKINS_WEBHOOK_SECRET (Authorization: Bearer or X-Jenkins-Token)
    when configured or in production/strict mode.
    """
    if not _verify_shared_token("JENKINS_WEBHOOK_SECRET", "X-Jenkins-Token"):
        logger.warning("[Webhook/Jenkins] Unauthorized request rejected.")
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    from app.validation import validate_webhook_jenkins
    cleaned, errors = validate_webhook_jenkins(data)
    if errors:
        return jsonify({"error": errors[0], "errors": errors}), 400

    run_id       = cleaned["run_id"]
    job_name     = cleaned["job_name"] or "CortexCICD/Self-Healing-CI-CD"
    build_number = cleaned["build_number"]
    result       = cleaned["result"]
    duration_ms  = cleaned["duration_ms"]
    console_log  = cleaned["console_log"]

    logger.info("[Webhook/Jenkins] Build event: %s → %s (build #%s)",
                run_id, result, build_number)

    try:
        from app.models import PipelineRun
        from app.db import db
        from app.healing import scheduler as healing_scheduler

        run = PipelineRun.query.filter_by(run_id=run_id).first()
        if not run:
            return jsonify({"error": f"Run {run_id} not found"}), 404

        # Only update runs that are still in progress
        if run.status != "In Progress":
            return jsonify({
                "status":  "skipped",
                "reason":  f"run already in terminal state: {run.status}",
                "run_id":  run_id,
            }), 200

        cortex_status = _jenkins_to_cortex_status(result)
        run.status    = cortex_status
        if duration_ms:
            run.duration_secs = max(1, duration_ms // 1000)
        if build_number:
            run.jenkins_build_number = build_number
        if job_name:
            run.jenkins_job_name = job_name

        db.session.add(run)
        db.session.commit()

        logger.info("[Webhook/Jenkins] %s updated to %s.", run_id, cortex_status)

        # Trigger healing for failed builds
        if cortex_status == "Failed":
            try:
                context = {}
                if console_log:
                    context["log_snippet"] = console_log[:2000]
                healing_scheduler.trigger_now(run_id, context)
            except Exception as exc:
                logger.warning("[Webhook/Jenkins] Could not trigger healing: %s", exc)

        return jsonify({
            "status":        "updated",
            "run_id":        run_id,
            "cortex_status": cortex_status,
        }), 200

    except Exception as exc:
        logger.error("[Webhook/Jenkins] Error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Prometheus Alertmanager Webhook ───────────────────────────────

@webhooks_bp.route("/prometheus", methods=["POST"])
def prometheus_webhook():
    """
    Receives Prometheus Alertmanager webhook payloads.
    Creates Alert records in the DB and, for critical infrastructure
    alerts, triggers the self-healing engine.

    Alertmanager webhook payload structure:
    {
      "status": "firing" | "resolved",
      "alerts": [
        {
          "status":      "firing",
          "labels":      {"alertname": "HighCPU", "severity": "critical", ...},
          "annotations": {"summary": "...", "description": "..."},
          "startsAt":    "2024-01-01T00:00:00Z",
        }
      ]
    }
    """
    if not _verify_shared_token("ALERTMANAGER_TOKEN", "X-Alertmanager-Token"):
        logger.warning("[Webhook/Prometheus] Unauthorized request rejected.")
        return jsonify({"error": "Unauthorized"}), 401

    data   = request.get_json(silent=True) or {}
    alerts = data.get("alerts", [])

    if not alerts:
        return jsonify({"status": "ok", "processed": 0}), 200

    try:
        from app.models import Alert
        from app.db import db

        created = 0
        healing_triggered = []

        for alert_data in alerts:
            labels      = alert_data.get("labels", {})
            annotations = alert_data.get("annotations", {})
            alert_name  = labels.get("alertname", "Unknown Alert")
            severity    = labels.get("severity", "medium").capitalize()
            status_str  = alert_data.get("status", "firing")
            summary     = annotations.get("summary", alert_name)

            cortex_status = "Active" if status_str == "firing" else "Resolved"

            # Resolve existing alert if Alertmanager sends resolved
            if cortex_status == "Resolved":
                existing = Alert.query.filter(
                    Alert.title.contains(alert_name),
                    Alert.status == "Active"
                ).first()
                if existing:
                    existing.status = "Resolved"
                    db.session.add(existing)
                    logger.info("[Webhook/Prometheus] Resolved alert: %s", alert_name)
                continue

            # Create new Active alert record
            new_alert = Alert(
                title=summary[:120],
                severity=severity if severity in ("Critical", "High", "Medium", "Low") else "Medium",
                source="Prometheus",
                status="Active",
                created_at=datetime.utcnow(),
            )
            db.session.add(new_alert)
            created += 1

            # Trigger healing for infra alerts that map to known failure types
            _try_healing_from_alert(labels, annotations, healing_triggered)

        db.session.commit()
        logger.info("[Webhook/Prometheus] Created %d alert(s), triggered healing: %s",
                    created, healing_triggered)

        return jsonify({
            "status":            "ok",
            "alerts_created":    created,
            "healing_triggered": healing_triggered,
        }), 201

    except Exception as exc:
        logger.error("[Webhook/Prometheus] Error: %s", exc)
        return jsonify({"error": str(exc)}), 500


def _try_healing_from_alert(labels: dict, annotations: dict, triggered: list):
    """
    Map Prometheus alert labels to CortexCICD failure types and
    trigger the healing engine for infrastructure alerts.
    """
    from app.validation import sanitize_k8s_identifier

    alert_name = labels.get("alertname", "").lower()
    pod_name   = sanitize_k8s_identifier(labels.get("pod") or labels.get("pod_name"), "cortex-api-pod")
    namespace  = sanitize_k8s_identifier(labels.get("namespace"), "default")
    deployment = sanitize_k8s_identifier(labels.get("deployment") or labels.get("app"), "cortex-api")

    # Map Prometheus alert names → healing contexts
    ALERT_MAP = {
        "oomkilled":           "OOM — Pod Evicted",
        "oom":                 "OOM — Pod Evicted",
        "cputhrottling":       "High CPU Saturation",
        "highcpu":             "High CPU Saturation",
        "podcrashlooping":     "CrashLoopBackOff",
        "crashloopbackoff":    "CrashLoopBackOff",
        "podrestart":          "Liveness Probe Fail",
        "livenessfailed":      "Liveness Probe Fail",
        "readinessfailed":     "Liveness Probe Fail",
    }

    matched_failure = None
    for keyword, failure_type in ALERT_MAP.items():
        if keyword in alert_name.replace("_", "").replace("-", ""):
            matched_failure = failure_type
            break

    if not matched_failure:
        return  # Not an infra alert we can auto-heal

    try:
        from app.db import db
        from app.models import PipelineRun
        from app.healing import scheduler as healing_scheduler

        # Create a unique synthetic run ID for infra-triggered healing
        run_id = f"INFRA-{int(datetime.utcnow().timestamp())}-{uuid.uuid4().hex[:6]}"
        run = PipelineRun(
            run_id=run_id,
            repo="CortexCICD/Self-Healing-CI-CD",
            branch="main",
            status="Failed",
            triggered_by="PrometheusAlert",
            duration_secs=0,
            risk_score=85,
            created_at=datetime.utcnow(),
        )
        db.session.add(run)
        db.session.flush()  # get ID without full commit

        context = {
            "failure_type":     matched_failure,
            "pod_name":         pod_name,
            "namespace":        namespace,
            "deployment_name":  deployment,
        }
        healing_scheduler.trigger_now(run_id, context)
        triggered.append({"run_id": run_id, "failure_type": matched_failure})

        logger.info("[Webhook/Prometheus] Triggered healing %s for alert: %s → %s",
                    run_id, labels.get("alertname"), matched_failure)
    except Exception as exc:
        logger.warning("[Webhook/Prometheus] Could not trigger healing: %s", exc)
