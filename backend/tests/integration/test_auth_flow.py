"""Integration tests for the POST /api/auth/token → GET /api/auth/me round-trip.

Plan 02 mounts the auth router under ``/api/auth`` so the existing ``POST /token``
became ``POST /api/auth/token`` and the existing ``GET /users/me`` became
``GET /api/auth/me``.
"""

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes.auth import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def test_login_and_get_me_round_trip(client: TestClient) -> None:
    """Full flow: log in via /api/auth/token, then fetch /api/auth/me with the token."""
    # Arrange + Act — log in
    login_response = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "admin"},
    )

    # Assert — 200 with access_token
    assert login_response.status_code == 200
    body = login_response.json()
    assert "access_token" in body
    access_token = body["access_token"]

    # Act — fetch /api/auth/me with the freshly minted token
    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Assert — 200 with the admin username
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["username"] == "admin"


def test_get_me_rejects_expired_token(client: TestClient) -> None:
    """GET /api/auth/me rejects a token whose ``exp`` claim is in the past."""
    # Arrange — craft a token that has already expired.
    expired_token = create_access_token(
        {"sub": "admin"},
        expires_delta=timedelta(seconds=-1),
    )

    # Act
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    # Assert — must be rejected with 401.
    assert response.status_code == 401
