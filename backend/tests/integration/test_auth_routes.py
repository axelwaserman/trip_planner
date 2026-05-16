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


@pytest.mark.integration
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


@pytest.mark.integration
def test_token_endpoint_rejects_wrong_password(client: TestClient) -> None:
    """POST /api/auth/token with wrong password returns 400."""
    response = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "wrongpassword"},
    )
    assert response.status_code == 400


@pytest.mark.integration
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


@pytest.mark.integration
def test_health_check_is_public(client: TestClient) -> None:
    """GET /health returns 200 without any auth token."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# GET /api/providers — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_providers_requires_auth(client: TestClient) -> None:
    """GET /api/providers returns 401 without Bearer token."""
    response = client.get("/api/providers")
    assert response.status_code == 401


@pytest.mark.integration
def test_get_providers_succeeds_with_valid_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """GET /api/providers returns 200 with a valid Bearer token."""
    response = client.get("/api/providers", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "ollama" in body


# ---------------------------------------------------------------------------
# POST /api/chat/session — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_session_requires_auth(client: TestClient) -> None:
    """POST /api/chat/session returns 401 without Bearer token."""
    response = client.post("/api/chat/session")
    assert response.status_code == 401


@pytest.mark.integration
def test_create_session_succeeds_with_valid_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """POST /api/chat/session returns 201 with a valid Bearer token."""
    response = client.post("/api/chat/session", headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body


# ---------------------------------------------------------------------------
# POST /api/chat — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_chat_requires_auth(client: TestClient) -> None:
    """POST /api/chat returns 401 without Bearer token."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello", "session_id": "fake-session"},
    )
    assert response.status_code == 401
