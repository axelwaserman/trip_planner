"""Failing test stubs for GET /api/auth/me — Plan 02 will mount this route.

These tests use ``@pytest.mark.xfail(strict=False)`` so the suite stays green while the
endpoint is absent. Once Plan 02 mounts ``GET /api/auth/me`` under the ``/api/auth``
prefix and the tests start passing, they will report XPASS and the executor must remove
the xfail marker.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes.auth import create_access_token

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


@pytest.mark.xfail(
    strict=False,
    reason="GET /api/auth/me not yet mounted — Plan 02 renames /users/me → /api/auth/me",
)
def test_auth_me_returns_401_without_token(client: TestClient) -> None:
    """GET /api/auth/me without a Bearer token returns 401 Unauthorized."""
    # Act
    response = client.get("/api/auth/me")

    # Assert
    assert response.status_code == 401


@pytest.mark.xfail(
    strict=False,
    reason="GET /api/auth/me not yet mounted — Plan 02 renames /users/me → /api/auth/me",
)
def test_auth_me_returns_200_with_valid_token(client: TestClient) -> None:
    """GET /api/auth/me with a valid Bearer token returns 200 + the username."""
    # Arrange
    token = create_access_token({"sub": "admin"})
    headers = {"Authorization": f"Bearer {token}"}

    # Act
    response = client.get("/api/auth/me", headers=headers)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "username" in body
    assert body["username"] == "admin"
