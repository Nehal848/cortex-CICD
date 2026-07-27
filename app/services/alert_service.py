"""
Alert Lifecycle Service
~~~~~~~~~~~~~~~~~~~~~~~~
Business logic for the Alert state machine.

Valid status transitions:
    Active → Acknowledged | Silenced | Resolved
    Acknowledged → Silenced | Resolved
    Silenced → Active (auto, when silenced_until expires) | Resolved
    Resolved → Archived

Each transition:
  1. Validates the current state allows the transition
  2. Updates the Alert record in the DB
  3. Emits an SSE event via app.events.publish()
  4. Returns (result_dict, http_status_code)
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_dict(alert) -> dict:
    return {
        "id":              alert.id,
        "title":           alert.title,
        "severity":        alert.severity,
        "source":          alert.source,
        "status":          alert.status,
        "timestamp":       alert.timestamp,
        "created_at":      alert.created_at.isoformat() if alert.created_at else None,
        "acknowledged_by": alert.acknowledged_by,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "resolved_by":     alert.resolved_by,
        "resolved_at":     alert.resolved_at.isoformat() if alert.resolved_at else None,
        "silenced_until":  alert.silenced_until.isoformat() if alert.silenced_until else None,
    }


def _emit(event_type: str, alert):
    """Best-effort SSE publish — never raises."""
    try:
        from app.events import publish
        publish(event_type, {
            "id":       alert.id,
            "title":    alert.title,
            "status":   alert.status,
            "severity": alert.severity,
        })
    except Exception as exc:
        logger.debug("[AlertService] SSE publish skipped: %s", exc)


def _get_alert(alert_id: int):
    """Fetch alert by id; returns (alert, None) or (None, error_dict)."""
    from app.models import Alert
    alert = Alert.query.get(alert_id)
    if not alert:
        return None, ({"error": f"Alert {alert_id} not found"}, 404)
    return alert, None


def _commit(alert):
    from app.db import db
    db.session.add(alert)
    db.session.commit()


# ── State transitions ──────────────────────────────────────────────

def acknowledge_alert(alert_id: int, user: str = "admin") -> tuple[dict, int]:
    """
    Transition: Active → Acknowledged.
    Sets acknowledged_by and acknowledged_at.
    """
    alert, err = _get_alert(alert_id)
    if err:
        return err

    if alert.status != "Active":
        return {"error": f"Cannot acknowledge alert in state '{alert.status}' (must be Active)"}, 409

    alert.status          = "Acknowledged"
    alert.acknowledged_by = user
    alert.acknowledged_at = _utcnow()
    _commit(alert)
    _emit("alert.updated", alert)

    logger.info("[AlertService] Alert %d acknowledged by %s.", alert_id, user)
    return _to_dict(alert), 200


def resolve_alert(alert_id: int, user: str = "admin") -> tuple[dict, int]:
    """
    Transition: Active | Acknowledged | Silenced → Resolved.
    Sets resolved_by and resolved_at.
    """
    alert, err = _get_alert(alert_id)
    if err:
        return err

    if alert.status not in ("Active", "Acknowledged", "Silenced"):
        return {"error": f"Cannot resolve alert in state '{alert.status}'"}, 409

    alert.status      = "Resolved"
    alert.resolved_by = user
    alert.resolved_at = _utcnow()
    _commit(alert)
    _emit("alert.updated", alert)

    logger.info("[AlertService] Alert %d resolved by %s.", alert_id, user)
    return _to_dict(alert), 200


def silence_alert(alert_id: int, duration_minutes: int = 60) -> tuple[dict, int]:
    """
    Transition: Active | Acknowledged → Silenced.
    Sets silenced_until to now + duration_minutes.
    Expired silences are auto-reversed to Active by get_active_alerts().
    """
    alert, err = _get_alert(alert_id)
    if err:
        return err

    if alert.status not in ("Active", "Acknowledged"):
        return {"error": f"Cannot silence alert in state '{alert.status}'"}, 409

    alert.status         = "Silenced"
    alert.silenced_until = _utcnow() + timedelta(minutes=duration_minutes)
    _commit(alert)
    _emit("alert.updated", alert)

    logger.info("[AlertService] Alert %d silenced for %d min.", alert_id, duration_minutes)
    return _to_dict(alert), 200


def archive_alert(alert_id: int) -> tuple[dict, int]:
    """
    Transition: Resolved → Archived.
    Removes alert from active views.
    """
    alert, err = _get_alert(alert_id)
    if err:
        return err

    if alert.status != "Resolved":
        return {"error": f"Cannot archive alert in state '{alert.status}' — must be Resolved first"}, 409

    alert.status = "Archived"
    _commit(alert)
    _emit("alert.updated", alert)

    logger.info("[AlertService] Alert %d archived.", alert_id)
    return _to_dict(alert), 200


# ── Queries ────────────────────────────────────────────────────────

def get_active_alerts() -> list[dict]:
    """
    Return all Active + Acknowledged alerts.
    Also auto-unsilences any Silenced alerts whose silenced_until has passed.
    """
    from app.models import Alert
    from app.db import db

    # Auto-unsilence expired alerts
    now     = _utcnow()
    expired = Alert.query.filter(
        Alert.status == "Silenced",
        Alert.silenced_until <= now,
    ).all()
    if expired:
        for a in expired:
            a.status         = "Active"
            a.silenced_until = None
            db.session.add(a)
            _emit("alert.updated", a)
        db.session.commit()
        logger.info("[AlertService] %d silenced alert(s) auto-unsilenced.", len(expired))

    alerts = Alert.query.filter(
        Alert.status.in_(["Active", "Acknowledged"])
    ).order_by(Alert.created_at.desc()).all()

    return [_to_dict(a) for a in alerts]


def get_alert_history(page: int = 1, per_page: int = 20) -> dict:
    """Return paginated Resolved + Archived alerts."""
    from app.models import Alert

    query = Alert.query.filter(
        Alert.status.in_(["Resolved", "Archived"])
    ).order_by(Alert.created_at.desc())

    total  = query.count()
    alerts = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "alerts":   [_to_dict(a) for a in alerts],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, (total + per_page - 1) // per_page),
    }
