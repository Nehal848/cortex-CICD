"""
tests/test_pipeline_service.py
"""
import pytest
from unittest.mock import patch
from app.services.pipeline_service import get_consecutive_failures, trigger_pipeline, update_run_status
from app.models import PipelineRun
from app.db import db


def test_get_consecutive_failures_empty_branch(app):
    assert get_consecutive_failures("org/repo", "new-branch") == 0


def test_get_consecutive_failures_counts_correctly(app):
    runs = [
        PipelineRun(run_id="R1", repo="org/repo", branch="main", status="Failed", triggered_by="M"),
        PipelineRun(run_id="R2", repo="org/repo", branch="main", status="Healed", triggered_by="M"),
        PipelineRun(run_id="R3", repo="org/repo", branch="main", status="Failed", triggered_by="M"),
        PipelineRun(run_id="R4", repo="other/repo", branch="main", status="Failed", triggered_by="M"),
    ]
    db.session.add_all(runs)
    db.session.commit()

    # R1 Failed, R2 Healed (counts as failure), R3 Failed = 3
    assert get_consecutive_failures("org/repo", "main") == 3


def test_get_consecutive_failures_resets_after_success(app):
    runs = [
        PipelineRun(run_id="R1", repo="org/repo", branch="main", status="Failed", triggered_by="M"),
        PipelineRun(run_id="R2", repo="org/repo", branch="main", status="Success", triggered_by="M"),
        PipelineRun(run_id="R3", repo="org/repo", branch="main", status="Failed", triggered_by="M"),
    ]
    db.session.add_all(runs)
    db.session.commit()

    # Resets at R2, only R3 counts
    assert get_consecutive_failures("org/repo", "main") == 1


def test_trigger_pipeline(app):
    result = trigger_pipeline("org/repo", "main")
    assert "run" in result
    run = result["run"]
    assert run.status == "In Progress"
    assert run.run_id.startswith("RUN-")
    
    in_db = PipelineRun.query.filter_by(run_id=run.run_id).first()
    assert in_db is not None


@patch("app.integrations.jenkins_client.get_build_status")
def test_update_run_status(mock_get_status, app):
    mock_get_status.return_value = {"building": False, "result": "SUCCESS", "duration_ms": 120000}
    run = PipelineRun(run_id="R1", repo="org/repo", branch="main", status="In Progress", triggered_by="M")
    db.session.add(run)
    db.session.commit()

    update_run_status("R1", 1, "job1")
    db.session.refresh(run)
    
    assert run.status == "Success"
    assert run.duration_secs == 120


@patch("app.integrations.jenkins_client.get_build_status")
def test_update_run_status_skips_if_not_in_progress(mock_get_status, app):
    run = PipelineRun(run_id="R1", repo="org/repo", branch="main", status="Healed", triggered_by="M")
    db.session.add(run)
    db.session.commit()

    update_run_status("R1", 1, "job1")
    db.session.refresh(run)
    
    assert run.status == "Healed"
    mock_get_status.assert_not_called()
