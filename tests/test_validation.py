"""
tests/test_validation.py — Input validation unit tests
No Flask context needed — pure function calls.
"""
import pytest
from app.validation import (
    validate_pipeline_run,
    validate_alert_silence,
    validate_security_scan,
    validate_k8s_scale,
    validate_analyze,
    validate_webhook_jenkins,
)


# ── validate_pipeline_run ──────────────────────────────────────────

def test_valid_pipeline_run():
    data, errors = validate_pipeline_run({"job_name": "org/repo", "branch": "main"})
    assert errors == []
    assert data["job_name"] == "org/repo"
    assert data["branch"]   == "main"


def test_missing_branch_is_error():
    _, errors = validate_pipeline_run({"job_name": "org/repo"})
    assert any("branch" in e for e in errors)


def test_missing_job_name_is_error():
    _, errors = validate_pipeline_run({"branch": "main"})
    assert any("job_name" in e for e in errors)


def test_invalid_repo_chars():
    _, errors = validate_pipeline_run({"job_name": "org repo!", "branch": "main"})
    assert any("invalid characters" in e for e in errors)


# ── validate_k8s_scale ─────────────────────────────────────────────

def test_valid_replicas():
    data, errors = validate_k8s_scale({"replicas": 3})
    assert errors == []
    assert data["replicas"] == 3


def test_replicas_zero_is_error():
    _, errors = validate_k8s_scale({"replicas": 0})
    assert any("replicas" in e for e in errors)


def test_replicas_eleven_is_error():
    _, errors = validate_k8s_scale({"replicas": 11})
    assert any("replicas" in e for e in errors)


def test_replicas_five_valid():
    data, errors = validate_k8s_scale({"replicas": 5})
    assert errors == []
    assert data["replicas"] == 5


# ── validate_alert_silence ─────────────────────────────────────────

def test_valid_silence_duration():
    data, errors = validate_alert_silence({"duration_minutes": 60})
    assert errors == []
    assert data["duration_minutes"] == 60


def test_silence_duration_zero_is_error():
    _, errors = validate_alert_silence({"duration_minutes": 0})
    assert errors


def test_silence_duration_negative_is_error():
    _, errors = validate_alert_silence({"duration_minutes": -1})
    assert errors


def test_silence_duration_over_week_is_error():
    _, errors = validate_alert_silence({"duration_minutes": 10_081})
    assert errors


# ── validate_analyze ──────────────────────────────────────────────

def test_valid_analyze():
    data, errors = validate_analyze({
        "failure_type": "OOM — Pod Evicted",
        "log_snippet": "OOMKilled",
        "run_id": "RUN-4819",
        "pod_restarts": 3,
        "risk_score": 85,
    })
    assert errors == []
    assert data["risk_score"] == 85


def test_risk_score_negative_is_error():
    _, errors = validate_analyze({"risk_score": -1})
    assert any("risk_score" in e for e in errors)


def test_risk_score_101_is_error():
    _, errors = validate_analyze({"risk_score": 101})
    assert any("risk_score" in e for e in errors)


def test_risk_score_boundary_values_ok():
    _, errors0  = validate_analyze({"risk_score": 0})
    _, errors100 = validate_analyze({"risk_score": 100})
    assert errors0   == []
    assert errors100 == []


# ── validate_security_scan ─────────────────────────────────────────

def test_valid_image_name():
    data, errors = validate_security_scan({"image": "cortex-api:latest"})
    assert errors == []
    assert data["image"] == "cortex-api:latest"


def test_default_image_used_when_missing():
    data, errors = validate_security_scan({})
    assert errors == []
    assert "cortex-api" in data["image"]


# ── validate_webhook_jenkins ───────────────────────────────────────

def test_valid_jenkins_webhook():
    data, errors = validate_webhook_jenkins({
        "run_id": "RUN-4820",
        "result": "SUCCESS",
        "duration_ms": 45000,
        "build_number": 143,
    })
    assert errors == []
    assert data["run_id"] == "RUN-4820"
    assert data["result"] == "SUCCESS"


def test_missing_run_id_is_error():
    _, errors = validate_webhook_jenkins({"result": "SUCCESS"})
    assert any("run_id" in e for e in errors)


def test_negative_duration_ms_is_error():
    _, errors = validate_webhook_jenkins({"run_id": "RUN-1", "result": "SUCCESS", "duration_ms": -1})
    assert any("duration_ms" in e for e in errors)
