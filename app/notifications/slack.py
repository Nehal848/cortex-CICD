"""
Slack Notifications
~~~~~~~~~~~~~~~~~~~~
Sends formatted messages to a Slack channel via Incoming Webhooks.
"""

import os
import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)


def send(message: str, title: str = "CortexCICD Alert", color: str = "danger",
         fields: list[dict] | None = None) -> bool:
    """
    Send a Slack notification via Incoming Webhook.

    Parameters
    ----------
    message : str   — main message text (supports Slack markdown)
    title   : str   — attachment title
    color   : str   — "danger" | "warning" | "good" | hex color
    fields  : list  — [{"title": str, "value": str, "short": bool}]

    Returns
    -------
    bool — True if sent successfully
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.debug("[Slack] SLACK_WEBHOOK_URL not set — notification skipped.")
        return False

    payload = {
        "attachments": [
            {
                "color":      color,
                "title":      title,
                "text":       message,
                "fields":     fields or [],
                "footer":     "CortexCICD Self-Healing Platform",
                "footer_icon": "https://raw.githubusercontent.com/CortexCICD/Self-Healing-CI-CD/main/app/static/images/logo.png",
                "ts":         _now_ts(),
            }
        ]
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(webhook_url, data=data,
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=5) as resp:
            ok = resp.status == 200
            if ok:
                logger.info("[Slack] Notification sent: %s", title)
            else:
                logger.warning("[Slack] Webhook returned %d", resp.status)
            return ok
    except URLError as exc:
        logger.error("[Slack] URLError: %s", exc)
        return False
    except Exception as exc:
        logger.error("[Slack] Unexpected error: %s", exc)
        return False


def send_failure(run_id: str, failure_type: str, risk_score: int, recommendations: list[str]) -> bool:
    fields = [
        {"title": "Run ID",       "value": run_id,       "short": True},
        {"title": "Failure Type", "value": failure_type, "short": True},
        {"title": "Risk Score",   "value": f"{risk_score}/100", "short": True},
        {"title": "Top Fix",      "value": recommendations[0] if recommendations else "See dashboard", "short": False},
    ]
    return send(
        message=f"Pipeline `{run_id}` has failed. Attempting auto-healing…",
        title="🚨 Pipeline Failure Detected",
        color="danger",
        fields=fields,
    )


def send_healed(run_id: str, strategy: str, duration_ms: int) -> bool:
    fields = [
        {"title": "Run ID",   "value": run_id,   "short": True},
        {"title": "Strategy", "value": strategy, "short": True},
        {"title": "Duration", "value": f"{duration_ms}ms", "short": True},
    ]
    return send(
        message=f"Pipeline `{run_id}` has been automatically healed using *{strategy}*.",
        title="✅ Self-Healing Successful",
        color="good",
        fields=fields,
    )


def send_escalation(run_id: str, failure_type: str) -> bool:
    return send(
        message=(f"⚠️ Pipeline `{run_id}` could not be automatically healed.\n"
                 f"Failure type: `{failure_type}`\n"
                 "Manual investigation required. Please check the CortexCICD dashboard."),
        title="🆘 Escalation Required",
        color="warning",
    )


def _now_ts() -> int:
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp())
