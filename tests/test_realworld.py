"""
Real-world readiness unit & integration tests for CortexCICD.

Verifies:
- Dynamic DATABASE_URL resolution (including postgres:// normalization) & dialect-safe migration
- Real Prometheus /metrics exposition & HTTP counters
- Programmatic Bearer / X-API-Key token generation and enforcement
- Database-backed User password verification blocking default fallback after override
- PlatformSetting GET/POST persistence, validation, and runtime HealingEngine policy gating
- GitHub push webhook commit telemetry extraction (files_changed, commit_message) & live ML risk_score
- Kubernetes apps/v1 ReplicaSet revision rollback (replacing deprecated spec.rollbackTo)
- TEE deterministic master key derivation & worker/WSGI entry-point sanity
"""

from __future__ import annotations

import os
import tempfile
import types
from unittest.mock import patch


def test_database_url_respected_and_dialect_migration():
    from app.app import create_app, _migrate_schema
    from app.models import PipelineRun, User, PlatformSetting

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        uri = f"sqlite:///{db_path}"
        with patch.dict(os.environ, {"DATABASE_URL": uri}):
            booted = create_app(test_config={"TESTING": True}, enable_background=False)
            assert booted.config["SQLALCHEMY_DATABASE_URI"] == uri
            with booted.app_context():
                # Re-running dialect-safe inspector migration is an idempotent no-op
                _migrate_schema()
                assert User.query.count() >= 1
                assert PlatformSetting.query.count() >= 6
                assert hasattr(PipelineRun, "files_changed")
                assert hasattr(PipelineRun, "commit_message")
    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass


def test_prometheus_metrics_endpoint_and_counters(anon_client):
    from app.observability import _PROMETHEUS_AVAILABLE

    anon_client.get("/healthz")
    res = anon_client.get("/metrics")
    assert res.status_code == 200
    body = res.data.decode("utf-8")
    if _PROMETHEUS_AVAILABLE:
        assert "flask_http_request_total" in body
        assert "cortex_sse_subscribers" in body
    else:
        assert "prometheus_client" in body


def test_bearer_token_and_x_api_key_authentication(anon_client, app):
    from werkzeug.security import generate_password_hash
    from app.db import db
    from app.models import User

    # Unauthenticated access stays blocked
    assert anon_client.get("/api/stats").status_code == 401

    # Seed user and generate token via authenticated session
    user = User(username="ops-bot", password_hash=generate_password_hash("Secret123!"), role="admin")
    db.session.add(user)
    db.session.commit()

    with anon_client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["username"] = "ops-bot"

    tok_res = anon_client.post("/api/auth/token")
    assert tok_res.status_code == 200
    token = tok_res.get_json()["token"]
    assert token.startswith("cx_")

    # Clear session cookie and verify POST /logout + Bearer auth succeeds
    assert anon_client.get("/logout").status_code == 405
    anon_client.post("/logout")
    assert anon_client.get("/api/stats").status_code == 401

    ok_res = anon_client.get("/api/stats", headers={"Authorization": f"Bearer {token}"})
    assert ok_res.status_code == 200

    # Invalid token fails
    bad_res = anon_client.get("/api/stats", headers={"Authorization": "Bearer wrong-token"})
    assert bad_res.status_code == 401

    # Static CORTEX_API_TOKEN also accepted via X-API-Key
    old_tok = app.config.get("CORTEX_API_TOKEN")
    app.config["CORTEX_API_TOKEN"] = "static-ci-key-999"
    try:
        key_res = anon_client.get("/api/stats", headers={"X-API-Key": "static-ci-key-999"})
        assert key_res.status_code == 200
    finally:
        app.config["CORTEX_API_TOKEN"] = old_tok


def test_db_user_password_login_blocks_default_when_changed(anon_client):
    from werkzeug.security import generate_password_hash
    from app.db import db
    from app.models import User

    db.session.add(User(username="admin", password_hash=generate_password_hash("HardenedPass!42"), role="admin"))
    db.session.commit()

    # Old default "admin" password must fail once DB password is non-default
    fail_res = anon_client.post("/login", data={"username": "admin", "password": "admin"})
    assert fail_res.status_code == 401
    assert b"Invalid username or password" in fail_res.data

    # Correct hashed password succeeds
    ok_res = anon_client.post("/login", data={"username": "admin", "password": "HardenedPass!42"})
    assert ok_res.status_code == 302


def test_platform_settings_persistence_and_healing_policy(client):
    from app.db import db
    from app.models import HealingEvent, PipelineRun, PlatformSetting
    from app.healing.engine import HealingEngine

    # Validation rejects out-of-range thresholds or non-http URLs
    bad_res = client.post("/api/settings", json={"cpu_threshold": 150})
    assert bad_res.status_code == 400
    bad_url = client.post("/api/settings", json={"jenkins_url": "ftp://invalid"})
    assert bad_url.status_code == 400

    # Save valid platform settings
    save_res = client.post("/api/settings", json={
        "cpu_threshold": 92,
        "slack_notifications": False,
        "auto_rollback": False,
        "jenkins_url": "https://jenkins.example.internal",
    })
    assert save_res.status_code == 200
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    settings = get_res.get_json()["settings"]
    assert settings["cpu_threshold"] == "92"
    assert settings["slack_notifications"] == "false"
    assert settings["auto_rollback"] == "false"
    assert PlatformSetting.get_bool("auto_rollback") is False

    # When auto_rollback is false, HealingEngine escalates instead of executing Rollback
    run = PipelineRun(
        run_id="RUN-9901",
        repo="org/app",
        branch="main",
        status="Failed",
        triggered_by="GitPush",
        duration_secs=45,
        risk_score=85,
    )
    db.session.add(run)
    db.session.commit()

    engine = HealingEngine(db, HealingEvent, PipelineRun)
    outcome = engine.handle_failure("RUN-9901", {"failure_type": "Dependency Resolution"})
    assert outcome["success"] is False
    assert outcome.get("escalated") is True


def test_github_webhook_extracts_diff_count_and_populates_ml_risk(anon_client):
    from app.models import PipelineRun

    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "org/cortex-service"},
        "pusher": {"name": "dev-alice"},
        "head_commit": {"message": "Refactor payment gateway & retry logic\n\nDetailed body"},
        "commits": [
            {
                "added": [f"src/new_{i}.py" for i in range(6)],
                "modified": [f"src/mod_{i}.py" for i in range(10)],
                "removed": ["src/old_1.py", "src/old_2.py"],
            }
        ],
    }
    res = anon_client.post(
        "/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "push"},
    )
    assert res.status_code == 201
    data = res.get_json()
    run = PipelineRun.query.filter_by(run_id=data["run_id"]).first()
    assert run is not None
    assert run.files_changed == 18
    assert run.commit_message == "Refactor payment gateway & retry logic"
    assert run.risk_score > 0


def test_k8s_apps_v1_replicaset_rollback(monkeypatch):
    from app.integrations import k8s_client

    patched_calls = []

    rs1 = types.SimpleNamespace(
        metadata=types.SimpleNamespace(
            annotations={"deployment.kubernetes.io/revision": "1"},
            owner_references=[types.SimpleNamespace(kind="Deployment", name="cortex-api")],
        ),
        spec=types.SimpleNamespace(template={"metadata": {"labels": {"ver": "v1"}}}),
    )
    rs2 = types.SimpleNamespace(
        metadata=types.SimpleNamespace(
            annotations={"deployment.kubernetes.io/revision": "2"},
            owner_references=[types.SimpleNamespace(kind="Deployment", name="cortex-api")],
        ),
        spec=types.SimpleNamespace(template={"metadata": {"labels": {"ver": "v2"}}}),
    )
    rs3 = types.SimpleNamespace(
        metadata=types.SimpleNamespace(
            annotations={"deployment.kubernetes.io/revision": "3"},
            owner_references=[types.SimpleNamespace(kind="Deployment", name="cortex-api")],
        ),
        spec=types.SimpleNamespace(template={"metadata": {"labels": {"ver": "v3"}}}),
    )
    dep = types.SimpleNamespace(
        metadata=types.SimpleNamespace(annotations={"deployment.kubernetes.io/revision": "3"}),
        spec=types.SimpleNamespace(selector=types.SimpleNamespace(match_labels={"app": "cortex-api"})),
    )

    class FakeAppsV1Api:
        def read_namespaced_deployment(self, name, namespace):
            return dep

        def list_namespaced_replica_set(self, namespace, label_selector):
            return types.SimpleNamespace(items=[rs1, rs3, rs2])

        def patch_namespaced_deployment(self, name, namespace, body):
            patched_calls.append((name, namespace, body))

    fake_k8s_client_mod = types.SimpleNamespace(AppsV1Api=FakeAppsV1Api)
    fake_k8s_pkg = types.SimpleNamespace(client=fake_k8s_client_mod)

    monkeypatch.setattr(k8s_client, "_load_config", lambda: True)
    with patch.dict("sys.modules", {"kubernetes": fake_k8s_pkg, "kubernetes.client": fake_k8s_client_mod}):
        res = k8s_client.rollback_deployment("cortex-api", namespace="cortex-system")

    assert res["success"] is True
    assert res["revision"] == 2
    assert len(patched_calls) == 1
    assert patched_calls[0][2] == {"spec": {"template": {"metadata": {"labels": {"ver": "v2"}}}}}


def test_tee_master_key_and_worker_entrypoint(monkeypatch):
    from app.tee import enclave
    import worker

    with patch.dict(os.environ, {"CORTEX_ENCLAVE_MASTER_KEY": "prod-kms-key-material"}):
        k1 = enclave._get_or_create_enclave_key()
        k2 = enclave._get_or_create_enclave_key()
        assert len(k1) == 32
        assert k1 == k2

    # Smoke-test worker orchestration with stubbed app creation & services
    called = []
    monkeypatch.setattr(worker, "create_app", lambda **kw: called.append(kw) or object())
    monkeypatch.setattr(worker.scheduler, "start", lambda *a: called.append("scheduler"))
    monkeypatch.setattr(worker.status_poller, "start", lambda *a: called.append("poller"))
    worker.main(run_once=True)
    assert called[0] == {"enable_background": False}
    assert "scheduler" in called
    assert "poller" in called


def test_webhooks_fail_closed_and_sanitize_labels(anon_client, app):
    from app.db import db
    from app.models import Alert, PipelineRun

    db.session.add(PipelineRun(
        run_id="RUN-777", repo="org/service", branch="main",
        status="In Progress", triggered_by="Jenkins",
    ))
    db.session.commit()

    old_strict = app.config.get("STRICT_WEBHOOK_VERIFICATION")
    old_jenkins = app.config.get("JENKINS_WEBHOOK_SECRET")
    old_prom = app.config.get("ALERTMANAGER_TOKEN")
    app.config["STRICT_WEBHOOK_VERIFICATION"] = True
    app.config["JENKINS_WEBHOOK_SECRET"] = "jenkins-secret-123"
    app.config["ALERTMANAGER_TOKEN"] = "prom-secret-456"
    try:
        # Missing/wrong token fails closed (401)
        j_fail = anon_client.post("/webhooks/jenkins", json={"run_id": "RUN-777", "result": "FAILURE"})
        assert j_fail.status_code == 401
        p_fail = anon_client.post("/webhooks/prometheus", json={"status": "firing", "alerts": []})
        assert p_fail.status_code == 401

        # Valid Jenkins secret succeeds
        j_ok = anon_client.post(
            "/webhooks/jenkins",
            headers={"X-Jenkins-Token": "jenkins-secret-123"},
            json={"run_id": "RUN-777", "result": "SUCCESS", "build_number": 77, "job_name": "org/service"},
        )
        assert j_ok.status_code == 200

        # Malicious K8s label values are sanitized and unique INFRA-* IDs avoid collision
        prom_payload = {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "KubePodCrashLooping", "severity": "critical", "pod": "api/../../etc$1", "namespace": "prod"},
                    "annotations": {"summary": "CrashLoopBackOff"},
                },
                {
                    "status": "firing",
                    "labels": {"alertname": "KubePodCrashLooping", "severity": "critical", "pod": "api-2", "namespace": "prod"},
                    "annotations": {"summary": "Second pod failing"},
                },
            ],
        }
        p_ok = anon_client.post(
            "/webhooks/prometheus",
            headers={"Authorization": "Bearer prom-secret-456"},
            json=prom_payload,
        )
        assert p_ok.status_code == 201
        infra_runs = PipelineRun.query.filter(PipelineRun.run_id.like("INFRA-%")).all()
        assert len(infra_runs) >= 2
        assert len({r.run_id for r in infra_runs}) == len(infra_runs)
        alerts = Alert.query.filter(Alert.title.contains("CrashLoopBackOff")).all()
        assert len(alerts) >= 1
    finally:
        app.config["STRICT_WEBHOOK_VERIFICATION"] = old_strict
        app.config["JENKINS_WEBHOOK_SECRET"] = old_jenkins
        app.config["ALERTMANAGER_TOKEN"] = old_prom


def test_security_scanners_fail_closed_and_ssrf_blocked(client, monkeypatch):
    from app.security import cosign

    # Simulate cosign binary installed & failing verification (must return verified=False, NOT mock pass)
    def _fake_cosign(cmd, **_kw):
        if len(cmd) > 1 and cmd[1] == "version":
            return types.SimpleNamespace(returncode=0, stdout="cosign v2.2.0", stderr="")
        return types.SimpleNamespace(returncode=1, stdout="", stderr="invalid signature")

    monkeypatch.setattr(cosign.subprocess, "run", _fake_cosign)
    res = cosign.verify_image_signature("cortex-api:latest")
    assert res["verified"] is False
    assert res["status"] == "FAILED"
    assert res["source"] == "cosign-cli"

    # Reject CLI flag injection, unsupported SBOM format, and key path traversal
    assert cosign.verify_image_signature("--key=/etc/passwd")["verified"] is False
    assert client.post("/api/security/sbom", json={"target": "app", "format": "yaml"}).status_code == 400
    assert client.post("/api/security/cosign/verify", json={"image": "nginx:1.25", "public_key": "../secret.pub"}).status_code == 400

    # SSRF guard blocks metadata IP in /api/settings
    ssrf_res = client.post("/api/settings", json={"prometheus_url": "http://169.254.169.254/latest/meta-data"})
    assert ssrf_res.status_code == 400


def test_token_expiration_and_revocation(anon_client):
    from datetime import datetime, timedelta
    from werkzeug.security import generate_password_hash
    from app.db import db
    from app.models import User

    db.session.add(User(
        username="token-user",
        password_hash=generate_password_hash("TokenSecret!99"),
        role="admin",
    ))
    db.session.commit()

    with anon_client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["username"] = "token-user"

    res = anon_client.post("/api/auth/token", json={"expires_days": 30})
    assert res.status_code == 200
    tok = res.get_json()["token"]
    assert res.get_json()["expires_at"] is not None

    # Force expiry into the past -> must reject
    user = User.query.filter_by(username="token-user").first()
    user.api_token_expires_at = datetime.utcnow() - timedelta(minutes=5)
    db.session.commit()

    anon_client.post("/logout")
    assert anon_client.get("/api/stats", headers={"Authorization": f"Bearer {tok}"}).status_code == 401

    # Re-issue token, verify access, then revoke via DELETE /api/auth/token
    with anon_client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["username"] = "token-user"
    res2 = anon_client.post("/api/auth/token")
    tok2 = res2.get_json()["token"]

    del_res = anon_client.delete("/api/auth/token")
    assert del_res.status_code == 200
    assert del_res.get_json()["status"] == "revoked"

    anon_client.post("/logout")
    assert anon_client.get("/api/stats", headers={"Authorization": f"Bearer {tok2}"}).status_code == 401


def test_login_brute_force_lockout_and_csrf_protection(anon_client, app):
    from app import http_security

    http_security._failed_logins.clear()
    for _ in range(5):
        r = anon_client.post("/login", data={"username": "brute-target", "password": "wrong"})
        assert r.status_code == 401
    locked = anon_client.post("/login", data={"username": "brute-target", "password": "wrong"})
    assert locked.status_code == 429
    http_security._failed_logins.clear()

    old_csrf = app.config.get("ENFORCE_CSRF")
    app.config["ENFORCE_CSRF"] = True
    try:
        with anon_client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "csrf-admin"
            sess["csrf_token"] = "csrf-test-token-value"

        # Cookie auth mutating call without CSRF token -> 403
        blocked = anon_client.post("/api/settings", json={"cpu_threshold": 82})
        assert blocked.status_code == 403

        # With valid X-CSRF-Token -> 200
        allowed = anon_client.post(
            "/api/settings",
            json={"cpu_threshold": 82},
            headers={"X-CSRF-Token": "csrf-test-token-value"},
        )
        assert allowed.status_code == 200
    finally:
        app.config["ENFORCE_CSRF"] = old_csrf


def test_ml_hmac_verification_and_worker_alert_dedup(app):
    from ml import predict_failure
    from app.models import Alert
    import worker

    predict_failure._load_or_train()
    assert predict_failure._SIG_PATH.exists()

    # Corrupt signature file -> must refuse cached pickle and retrain validly
    predict_failure._SIG_PATH.write_text("tampered-signature", encoding="utf-8")
    predict_failure._model = None
    assert predict_failure._load_or_train() is True
    raw = predict_failure._MODEL_PATH.read_bytes()
    assert predict_failure._verify_model_bytes(raw) is True

    # Worker threshold alerting creates once and deduplicates subsequent tick
    first = worker._check_resource_thresholds(app, 96.0, 91.0)
    second = worker._check_resource_thresholds(app, 97.0, 93.0)
    assert len(first) == 2
    assert len(second) == 0
    assert Alert.query.filter(Alert.status == "Active", Alert.title.like("High CPU Usage%")).count() >= 1


def test_http_security_headers_and_proxyfix(anon_client, app):
    # Standard responses contain hardening headers
    resp = anon_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # When SESSION_COOKIE_SECURE is true, HSTS header is added
    old_sec = app.config.get("SESSION_COOKIE_SECURE")
    app.config["SESSION_COOKIE_SECURE"] = True
    try:
        sec_resp = anon_client.get("/healthz")
        assert "Strict-Transport-Security" in sec_resp.headers
    finally:
        app.config["SESSION_COOKIE_SECURE"] = old_sec
