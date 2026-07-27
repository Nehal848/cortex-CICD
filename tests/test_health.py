"""
tests/test_health.py — Health endpoint tests
"""
import json
import pytest
from tests.conftest import _TEST_CONFIG
from app.app import create_app


@pytest.fixture
def client():
    app = create_app(test_config=_TEST_CONFIG)
    with app.test_client() as c:
        yield c


def test_healthz_always_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert json.loads(r.data)["status"] == "ok"


def test_readyz_200_when_db_ready(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert d["status"] == "ok"
    assert "database" in d["checks"]


def test_readyz_contains_all_checks(client):
    r = client.get("/readyz")
    d = json.loads(r.data)
    assert set(d["checks"].keys()) >= {"database", "healing_scheduler", "status_poller"}


def test_livez_200_with_all_components(client):
    r = client.get("/livez")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert "components" in d
    expected = {"database", "healing_scheduler", "jenkins", "ml_model", "status_poller"}
    assert expected.issubset(d["components"].keys())


def test_livez_uptime_is_positive_integer(client):
    r = client.get("/livez")
    d = json.loads(r.data)
    assert isinstance(d["uptime_secs"], int)
    assert d["uptime_secs"] >= 0
