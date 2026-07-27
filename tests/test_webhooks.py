"""
tests/test_webhooks.py
"""
import json
import pytest
from app.models import PipelineRun, Alert
from app.db import db


def test_github_ping(anon_client):
    r = anon_client.post("/webhooks/github", data=b"{}", content_type="application/json", headers={"X-GitHub-Event": "ping"})
    assert r.status_code == 200
    assert json.loads(r.data)["status"] == "pong"


def test_github_unknown_event(anon_client):
    r = anon_client.post("/webhooks/github", data=b"{}", content_type="application/json", headers={"X-GitHub-Event": "star"})
    assert r.status_code == 200
    assert json.loads(r.data)["status"] == "ignored"


def test_github_push_creates_run(anon_client):
    payload = {
        "repository": {"full_name": "org/repo"},
        "ref": "refs/heads/feature-1"
    }
    r = anon_client.post(
        "/webhooks/github", 
        data=json.dumps(payload).encode(), 
        content_type="application/json", 
        headers={"X-GitHub-Event": "push"}
    )
    assert r.status_code == 201
    
    # Verify in DB
    run = PipelineRun.query.filter_by(repo="org/repo", branch="feature-1").first()
    assert run is not None
    assert run.triggered_by == "GitPush"


def test_jenkins_missing_run_id(anon_client):
    r = anon_client.post("/webhooks/jenkins", json={"result": "SUCCESS"})
    assert r.status_code == 400


def test_jenkins_success_updates_run(anon_client):
    # Setup In Progress run
    run = PipelineRun(run_id="RUN-999", repo="r", branch="b", status="In Progress", triggered_by="M")
    db.session.add(run)
    db.session.commit()

    r = anon_client.post("/webhooks/jenkins", json={
        "run_id": "RUN-999",
        "result": "SUCCESS",
        "duration_ms": 1000
    })
    assert r.status_code == 200
    
    db.session.refresh(run)
    assert run.status == "Success"
    assert run.duration_secs == 1


def test_prometheus_firing_creates_alert(anon_client):
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighCPU", "severity": "critical"},
                "annotations": {"summary": "CPU is 99%"}
            }
        ]
    }
    r = anon_client.post("/webhooks/prometheus", json=payload)
    assert r.status_code == 201
    
    a = Alert.query.filter_by(title="CPU is 99%").first()
    assert a is not None
    assert a.status == "Active"
    assert a.severity == "Critical"


def test_prometheus_resolved_resolves_alert(anon_client):
    # Setup Active alert
    a = Alert(title="HighCPU", severity="critical", source="Prometheus", status="Active")
    db.session.add(a)
    db.session.commit()

    payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "HighCPU", "severity": "critical"}
            }
        ]
    }
    r = anon_client.post("/webhooks/prometheus", json=payload)
    assert r.status_code == 201
    
    db.session.refresh(a)
    assert a.status == "Resolved"
