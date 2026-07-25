"""
Notification Dispatcher
~~~~~~~~~~~~~~~~~~~~~~~~
Central dispatcher called by the healing engine and API routes.
Fans out to all configured channels (Slack, Email) in one call.
"""

import logging

logger = logging.getLogger(__name__)


def notify(event_type: str, payload: dict) -> dict:
    """
    Dispatch a notification to all configured channels.

    Parameters
    ----------
    event_type : str — "failure" | "healed" | "escalation" | "security"
    payload    : dict — event-specific data

    Returns
    -------
    dict — {slack_sent, email_sent}
    """
    from . import slack, email as _email

    results = {"slack_sent": False, "email_sent": False}

    run_id       = payload.get("run_id", "UNKNOWN")
    failure_type = payload.get("failure_type", "Unknown")
    strategy     = payload.get("strategy", "Unknown")
    outcome      = payload.get("outcome", "Unknown")
    risk_score   = payload.get("risk_score", 0)
    duration_ms  = payload.get("duration_ms", 0)
    recommendations = payload.get("recommendations", [])

    if event_type == "failure":
        results["slack_sent"] = slack.send_failure(run_id, failure_type, risk_score, recommendations)
        results["email_sent"] = _email.send_failure_email(run_id, failure_type, recommendations, risk_score)

    elif event_type == "healed":
        results["slack_sent"] = slack.send_healed(run_id, strategy, duration_ms)
        results["email_sent"] = _email.send_healing_report(run_id, strategy, outcome, duration_ms)

    elif event_type == "escalation":
        results["slack_sent"] = slack.send_escalation(run_id, failure_type)
        results["email_sent"] = _email.send_failure_email(
            run_id, failure_type,
            ["⚠️ All automated healing strategies exhausted.", "Manual investigation required."],
            risk_score=90,
        )

    elif event_type == "security":
        image  = payload.get("image", "unknown")
        crit   = payload.get("critical", 0)
        high   = payload.get("high", 0)
        results["slack_sent"] = slack.send(
            message=f"Security scan of `{image}` found *{crit} Critical* and *{high} High* vulnerabilities.",
            title="🔒 Security Scan Alert",
            color="danger" if crit > 0 else "warning",
        )
    else:
        logger.warning("[Dispatcher] Unknown event_type: %s", event_type)

    logger.info("[Dispatcher] Notified: event=%s slack=%s email=%s",
                event_type, results["slack_sent"], results["email_sent"])
    return results
