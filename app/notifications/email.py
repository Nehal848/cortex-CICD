"""
Email Notifications
~~~~~~~~~~~~~~~~~~~~
Sends HTML-formatted emails via SMTP (Gmail, SendGrid, etc.)
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    return {
        "host":  os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":  int(os.getenv("SMTP_PORT", "587")),
        "user":  os.getenv("SMTP_USER", ""),
        "pass":  os.getenv("SMTP_PASS", ""),
        "to":    os.getenv("ALERT_EMAIL_TO", ""),
    }


def _is_configured() -> bool:
    cfg = _get_config()
    return bool(cfg["user"] and cfg["pass"] and cfg["to"])


def send(subject: str, html_body: str, plain_body: str = "") -> bool:
    """
    Send an HTML email.

    Returns True on success, False otherwise.
    Silently skips if SMTP is not configured.
    """
    if not _is_configured():
        logger.debug("[Email] SMTP not configured — email skipped.")
        return False

    cfg = _get_config()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"CortexCICD <{cfg['user']}>"
    msg["To"]      = cfg["to"]

    if plain_body:
        msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.starttls()
            server.login(cfg["user"], cfg["pass"])
            server.sendmail(cfg["user"], cfg["to"], msg.as_string())
        logger.info("[Email] Sent: %s → %s", subject, cfg["to"])
        return True
    except smtplib.SMTPException as exc:
        logger.error("[Email] SMTP error: %s", exc)
        return False
    except Exception as exc:
        logger.error("[Email] Unexpected error: %s", exc)
        return False


def send_failure_email(run_id: str, failure_type: str, recommendations: list[str],
                       risk_score: int = 0) -> bool:
    html = _failure_template(run_id, failure_type, recommendations, risk_score)
    return send(
        subject=f"🚨 CortexCICD — Pipeline {run_id} Failed",
        html_body=html,
        plain_body=f"Pipeline {run_id} failed. Type: {failure_type}. Risk: {risk_score}/100.",
    )


def send_healing_report(run_id: str, strategy: str, outcome: str, duration_ms: int) -> bool:
    icon = "✅" if outcome == "Resolved" else "❌"
    html = _healing_template(run_id, strategy, outcome, duration_ms)
    return send(
        subject=f"{icon} CortexCICD — Healing Report for {run_id}",
        html_body=html,
        plain_body=f"Healing result for {run_id}: {outcome} via {strategy} in {duration_ms}ms.",
    )


# ── HTML Templates ─────────────────────────────────────────────────

def _base(content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><style>
  body{{font-family:Inter,Arial,sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:20px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px;max-width:600px;margin:auto}}
  .header{{font-size:20px;font-weight:700;margin-bottom:16px;color:#58a6ff}}
  .row{{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #21262d}}
  .label{{color:#8b949e;font-size:13px}}
  .value{{font-weight:600;font-size:13px}}
  .critical{{color:#f85149}} .high{{color:#d29922}} .good{{color:#3fb950}}
  .rec-list{{list-style:none;padding:0}} .rec-list li{{padding:6px 0;font-size:13px;color:#8b949e}}
  .rec-list li::before{{content:"→ ";color:#58a6ff}}
  .footer{{margin-top:20px;font-size:11px;color:#484f58;text-align:center}}
</style></head>
<body><div class="card">{content}<div class="footer">CortexCICD Self-Healing Platform · {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</div></div></body>
</html>"""


def _failure_template(run_id, failure_type, recommendations, risk_score):
    rec_items = "".join(f"<li>{r}</li>" for r in recommendations)
    color = "critical" if risk_score >= 75 else ("high" if risk_score >= 50 else "good")
    return _base(f"""
    <div class="header">🚨 Pipeline Failure Detected</div>
    <div class="row"><span class="label">Run ID</span><span class="value">{run_id}</span></div>
    <div class="row"><span class="label">Failure Type</span><span class="value class-{color}">{failure_type}</span></div>
    <div class="row"><span class="label">Risk Score</span><span class="value {color}">{risk_score}/100</span></div>
    <div style="margin-top:16px"><div class="label" style="margin-bottom:8px">Recommendations</div>
    <ul class="rec-list">{rec_items}</ul></div>
    """)


def _healing_template(run_id, strategy, outcome, duration_ms):
    color = "good" if outcome == "Resolved" else "critical"
    return _base(f"""
    <div class="header">{'✅' if outcome == 'Resolved' else '❌'} Healing Report</div>
    <div class="row"><span class="label">Run ID</span><span class="value">{run_id}</span></div>
    <div class="row"><span class="label">Strategy</span><span class="value">{strategy}</span></div>
    <div class="row"><span class="label">Outcome</span><span class="value {color}">{outcome}</span></div>
    <div class="row"><span class="label">Duration</span><span class="value">{duration_ms} ms</span></div>
    """)
