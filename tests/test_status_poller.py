"""
tests/test_status_poller.py
"""
import pytest
from app.services.status_poller import is_running, start, _poll_once
from app.models import PipelineRun
from app.db import db





def test_is_running_true_after_start(app):
    start(app, db)
    assert is_running()


def test_poll_resolves_mock_success(app, monkeypatch):
    # Mock jenkins client
    import app.integrations.jenkins_client as jc
    monkeypatch.setattr(jc, "get_build_status", lambda j, b: {"building": False, "result": "SUCCESS", "duration_ms": 15000})

    run = PipelineRun(
        run_id="R1", repo="org/repo", branch="main", status="In Progress", 
        triggered_by="M", jenkins_job_name="job", jenkins_build_number=1
    )
    db.session.add(run)
    db.session.commit()

    start(app, db)
    _poll_once()
    
    db.session.refresh(run)
    assert run.status == "Success"
    assert run.duration_secs == 15


def test_poll_resolves_mock_failure(app, monkeypatch):
    import app.integrations.jenkins_client as jc
    monkeypatch.setattr(jc, "get_build_status", lambda j, b: {"building": False, "result": "FAILURE", "duration_ms": 20000})

    # Mock healing scheduler to prevent errors during test
    import app.healing.scheduler as hs
    monkeypatch.setattr(hs, "trigger_now", lambda r: None)

    run = PipelineRun(
        run_id="R2", repo="org/repo", branch="main", status="In Progress", 
        triggered_by="M", jenkins_job_name="job", jenkins_build_number=2
    )
    db.session.add(run)
    db.session.commit()

    start(app, db)
    _poll_once()
    
    db.session.refresh(run)
    assert run.status == "Failed"
    assert run.duration_secs == 20


def test_poll_ignores_still_building(app, monkeypatch):
    import app.integrations.jenkins_client as jc
    monkeypatch.setattr(jc, "get_build_status", lambda j, b: {"building": True, "result": None, "duration_ms": 0})

    run = PipelineRun(
        run_id="R3", repo="org/repo", branch="main", status="In Progress", 
        triggered_by="M", jenkins_job_name="job", jenkins_build_number=3
    )
    db.session.add(run)
    db.session.commit()

    start(app, db)
    _poll_once()
    
    db.session.refresh(run)
    assert run.status == "In Progress"
