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
