"""
tests/test_alert_lifecycle.py
"""
import json
import pytest
from app.models import Alert
from app.db import db


def test_active_alerts_returns_only_active_and_acknowledged(client):
    # Setup DB state
    a1 = Alert(title="A1", severity="High", source="Prometheus", status="Active")
    a2 = Alert(title="A2", severity="High", source="Prometheus", status="Acknowledged")
    a3 = Alert(title="A3", severity="High", source="Prometheus", status="Silenced")
    a4 = Alert(title="A4", severity="High", source="Prometheus", status="Resolved")
    db.session.add_all([a1, a2, a3, a4])
    db.session.commit()

    r = client.get("/api/alerts/active")
    assert r.status_code == 200
    data = json.loads(r.data)["alerts"]
    assert len(data) == 2
    statuses = {a["status"] for a in data}
    assert statuses == {"Active", "Acknowledged"}


def test_acknowledge_alert_sets_fields(client):
    a = Alert(title="A1", severity="High", source="Prometheus", status="Active")
    db.session.add(a)
    db.session.commit()

    r = client.post(f"/api/alerts/{a.id}/acknowledge", json={"user": "test_user"})
    assert r.status_code == 200
    
    # Check DB
    db.session.refresh(a)
    assert a.status == "Acknowledged"
    assert a.acknowledged_by == "test_user"
    assert a.acknowledged_at is not None


def test_double_acknowledge_returns_409(client):
    a = Alert(title="A1", severity="High", source="Prometheus", status="Acknowledged")
    db.session.add(a)
    db.session.commit()

    r = client.post(f"/api/alerts/{a.id}/acknowledge", json={})
    assert r.status_code == 409


def test_resolve_alert_transitions_correctly(client):
    a = Alert(title="A1", severity="High", source="Prometheus", status="Acknowledged")
    db.session.add(a)
    db.session.commit()

    r = client.post(f"/api/alerts/{a.id}/resolve", json={"user": "admin2"})
    assert r.status_code == 200
    
    db.session.refresh(a)
    assert a.status == "Resolved"
    assert a.resolved_by == "admin2"
    assert a.resolved_at is not None


def test_resolve_nonexistent_alert_404(client):
    r = client.post("/api/alerts/999/resolve", json={})
    assert r.status_code == 404


def test_silence_alert_sets_silenced_until(client):
    a = Alert(title="A1", severity="High", source="Prometheus", status="Active")
    db.session.add(a)
    db.session.commit()

    r = client.post(f"/api/alerts/{a.id}/silence", json={"duration_minutes": 30})
    assert r.status_code == 200
    
    db.session.refresh(a)
    assert a.status == "Silenced"
    assert a.silenced_until is not None


def test_invalid_duration_returns_400(client):
    a = Alert(title="A1", severity="High", source="Prometheus", status="Active")
    db.session.add(a)
    db.session.commit()

    r = client.post(f"/api/alerts/{a.id}/silence", json={"duration_minutes": 0})
    assert r.status_code == 400


def test_history_returns_paginated_resolved_archived(client):
    for i in range(25):
        db.session.add(Alert(title=f"A{i}", severity="Low", source="src", status="Resolved"))
    db.session.commit()

    r = client.get("/api/alerts/history?page=1&per_page=10")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert len(d["alerts"]) == 10
    assert d["total"] == 25
    assert d["pages"] == 3


def test_archive_from_resolved_state(client):
    a = Alert(title="A1", severity="High", source="Prometheus", status="Resolved")
    db.session.add(a)
    db.session.commit()

    r = client.post(f"/api/alerts/{a.id}/archive", json={})
    assert r.status_code == 200
    
    db.session.refresh(a)
    assert a.status == "Archived"
