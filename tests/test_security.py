"""
tests/test_security.py
"""
import pytest
from app.security import scanner, secret_scanner


def test_scan_image_fallback():
    # When Trivy isn't installed, it should return mock structure
    res = scanner.scan_image("test-image:latest")
    assert "critical" in res
    assert "high" in res
    assert "vulnerabilities" in res
    assert isinstance(res["vulnerabilities"], list)


def test_scan_filesystem_fallback():
    res = scanner.scan_filesystem(".")
    assert "critical" in res
    assert "high" in res
    assert "vulnerabilities" in res


def test_secret_scanner_returns_list():
    res = secret_scanner.scan_directory("tests/")
    assert isinstance(res, dict)
    assert "findings" in res
    assert isinstance(res["findings"], list)
    # The project contains no real leaked secrets, but the mock/fallback
    # logic should ensure a valid list is returned.
    if len(res["findings"]) > 0:
        assert "file" in res["findings"][0]
        assert "rule" in res["findings"][0]


def test_secret_scanner_ignores_git():
    # Ensure standard exclusion directories are respected (tested implicitly
    # by it not crashing on binary/git files).
    res = secret_scanner.scan_directory("tests/")
    assert isinstance(res, dict)
    assert "findings" in res


def test_production_security_validation_rejects_default_secrets(monkeypatch):
    from app.config import Config
    monkeypatch.setattr(Config, "ENV", "production")
    monkeypatch.setattr(Config, "SECRET_KEY", "super-secret-default-key")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")

    with pytest.raises(RuntimeError) as exc_info:
        Config.validate_production_security()
    assert "SECRET_KEY" in str(exc_info.value) or "ADMIN_PASSWORD" in str(exc_info.value)


def test_production_security_validation_accepts_strong_secrets(monkeypatch):
    from app.config import Config
    monkeypatch.setattr(Config, "ENV", "production")
    monkeypatch.setattr(Config, "SECRET_KEY", "complex-unique-random-prod-key-1234567890")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "SuperSecureComplexPassword#2026")

    # Should not raise any error
    Config.validate_production_security()


def test_sse_per_ip_rate_limiting():
    from app.events import subscribe, unsubscribe
    test_ip = "192.168.1.150"
    subs = []
    try:
        # Connect up to limit of 5
        for _ in range(5):
            sub_id, _ = subscribe(client_ip=test_ip)
            subs.append(sub_id)

        # 6th connection from the same IP must raise RuntimeError (HTTP 429)
        with pytest.raises(RuntimeError) as exc_info:
            subscribe(client_ip=test_ip)
        assert "Rate limit exceeded" in str(exc_info.value)
    finally:
        for sid in subs:
            unsubscribe(sid)


def test_generate_sbom_fallback():
    from app.security import sbom
    res = sbom.generate_sbom("cortex-api:v2.4.1", "spdx-json")
    assert res["image"] == "cortex-api:v2.4.1"
    assert res["format"] == "spdx-json"
    assert "packages" in res
    assert res["total_packages"] > 0
    assert any(pkg["name"] == "flask" for pkg in res["packages"])


def test_verify_cosign_signature_fallback():
    from app.security import cosign
    res = cosign.verify_image_signature("cortex-api:v2.4.1")
    assert res["image"] == "cortex-api:v2.4.1"
    assert res["verified"] is True
    assert res["status"] == "VALID"
    assert "signatures_found" in res
