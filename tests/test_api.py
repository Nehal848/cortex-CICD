import pytest
from app.app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        # Mock logged-in session for API tests
        with client.session_transaction() as sess:
            sess["logged_in"] = True
        yield client

def test_index_page(client):
    """Verify that the landing page renders correctly."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Cortex CI/CD" in response.data

def test_dashboard_page(client):
    """Verify that the dashboard page renders."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Dashboard | Cortex CI/CD" in response.data

def test_api_stats(client):
    """Verify that the stats API returns JSON metrics."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.get_json()
    assert "success_rate" in data
    assert "total_deps" in data

def test_api_predict(client):
    """Verify ML prediction API."""
    response = client.get("/api/predict/RUN-4816")
    assert response.status_code == 200
    data = response.get_json()
    assert "risk_score" in data
    assert "failure_type" in data
    assert "confidence" in data
    assert "recommended_action" in data

def test_api_analyze(client):
    """Verify RCA analysis API."""
    payload = {
        "failure_type": "OOM \u2014 Pod Evicted",
        "log_snippet": "OOMKilled: memory limit exceeded",
        "run_id": "RUN-4816"
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert "root_cause" in data
    assert "recommendations" in data
    assert "evidence" in data

def test_api_tee_status(client):
    """Verify TEE status API."""
    response = client.get("/api/tee/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["overall_status"] == "Secure"
    assert "enclave" in data

def test_api_security_sbom(client):
    """Verify Syft SBOM generation endpoint."""
    response = client.post("/api/security/sbom", json={"image": "cortex-api:v2.4.1"})
    assert response.status_code == 200
    data = response.get_json()
    assert "packages" in data
    assert data["image"] == "cortex-api:v2.4.1"

def test_api_security_cosign_verify(client):
    """Verify Cosign verification endpoint."""
    response = client.post("/api/security/cosign/verify", json={"image": "cortex-api:v2.4.1"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["verified"] is True
    assert data["status"] == "VALID"
