import pytest
from app.app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Verify that the landing page renders correctly."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Cortex CI/CD" in response.data

def test_api_stats_unauthorized(client):
    """Verify that the API requires login."""
    response = client.get("/api/stats")
    assert response.status_code == 401
