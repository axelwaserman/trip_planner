"""Integration tests for authentication — /api/auth/token endpoint and protected routes."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client with lifespan."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /api/auth/token
# ---------------------------------------------------------------------------


def test_token_endpoint_returns_jwt_for_valid_credentials(client: TestClient) -> None:
    """POST /api/auth/token with valid credentials returns access_token and token_type."""
    response = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    # Token must be a non-trivial JWT (three dot-separated segments)
    parts = body["access_token"].split(".")
    assert len(parts) == 3


def test_token_endpoint_rejects_wrong_password(client: TestClient) -> None:
    """POST /api/auth/token with wrong password returns 400."""
    response = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "wrongpassword"},
    )
    assert response.status_code == 400


def test_token_endpoint_rejects_unknown_user(client: TestClient) -> None:
    """POST /api/auth/token with unknown username returns 400."""
    response = client.post(
        "/api/auth/token",
        data={"username": "nobody", "password": "secret"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /health — must remain public
# ---------------------------------------------------------------------------


def test_health_check_is_public(client: TestClient) -> None:
    """GET /health returns 200 without any auth token.

    Plan 07-05 (D-06) extended the response shape with ``flight_provider``;
    we assert the public-access invariant via field-membership checks rather
    than exact-equality so future additions don't break this test again.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["flight_provider"] in ("real", "mock")


# ---------------------------------------------------------------------------
# GET /api/providers — requires auth
# ---------------------------------------------------------------------------


def test_get_providers_requires_auth(client: TestClient) -> None:
    """GET /api/providers returns 401 without Bearer token."""
    response = client.get("/api/providers")
    assert response.status_code == 401


def test_get_providers_succeeds_with_valid_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    """GET /api/providers returns 200 with a valid Bearer token."""
    response = client.get("/api/providers", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "ollama" in body


# ---------------------------------------------------------------------------
# POST /api/chat/conversation — requires auth
# ---------------------------------------------------------------------------


def test_create_session_requires_auth(client: TestClient) -> None:
    """POST /api/chat/conversation returns 401 without Bearer token."""
    response = client.post("/api/chat/conversation")
    assert response.status_code == 401


def test_create_session_succeeds_with_valid_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /api/chat/conversation returns 201 with a valid Bearer token."""
    response = client.post("/api/chat/conversation", headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert "conversation_id" in body


# ---------------------------------------------------------------------------
# POST /api/chat — requires auth
# ---------------------------------------------------------------------------


def test_chat_requires_auth(client: TestClient) -> None:
    """POST /api/chat returns 401 without Bearer token."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello", "conversation_id": "fake-session"},
    )
    assert response.status_code == 401
