"""Test health check endpoint.

Phase 7 / Plan 07-05 (D-06): /health returns ``flight_provider`` alongside
``status``. The lifespan must run for ``app.state.flight_provider`` to be
populated, so we use ``with TestClient(app) as client:`` (the bare module-level
``TestClient(app)`` constructor does NOT trigger the lifespan).
"""

from fastapi.testclient import TestClient

from app.api.main import app


def test_health() -> None:
    """/health returns the post-Plan-07-05 shape: status + flight_provider."""
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "flight_provider" in data
    assert data["flight_provider"] in ("real", "mock")


def test_health_flight_provider_is_mock_without_credentials() -> None:
    """Default test env has no AMADEUS_* creds -> flight_provider == "mock".

    The integration ``conftest.py`` does not pre-populate ``AMADEUS_*`` env
    vars, so the lifespan branch hits the missing-creds fallback and reports
    ``flight_provider == "mock"`` on /health.
    """
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["flight_provider"] == "mock"
