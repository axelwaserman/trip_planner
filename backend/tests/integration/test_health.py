"""Test health check endpoint."""

from fastapi.testclient import TestClient

from backend.app.api.main import app

client = TestClient(app)


def test_health() -> None:
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
