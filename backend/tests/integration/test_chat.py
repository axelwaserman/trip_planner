"""Test chat endpoint."""

import json
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes.auth import create_access_token
from app.chat.models import ContentEvent, StreamEvent


@pytest.fixture
def client() -> TestClient:
    """Create test client with lifespan."""
    with TestClient(app) as c:
        yield c


def test_chat_endpoint_requires_session_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat endpoint requires session_id."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello"},
        headers=auth_headers,
    )
    # FastAPI returns 422 for missing required fields
    assert response.status_code == 422


def test_chat_endpoint_rejects_invalid_session(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat endpoint rejects invalid session.

    Per CR-02 the route raises a 404 at the boundary (before any SSE stream
    starts) when the session doesn't exist OR is owned by another user. The
    same shape is used so a non-owner can't probe for session existence.
    """
    response = client.post(
        "/api/chat",
        json={"message": "Hello", "session_id": "invalid-session"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_chat_endpoint_streams_response(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat endpoint returns streaming response."""

    # Create a session first
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201  # Created
    session_id = session_response.json()["session_id"]

    async def mock_stream(message: str, session_id: str) -> AsyncGenerator[StreamEvent]:
        """Mock async generator for streaming."""
        yield ContentEvent(
            chunk="Hello there!",
            session_id=session_id,
        )

    # Patch the ChatService.chat_stream method (patch the real definition location)
    with patch("app.chat.service.ChatService.chat_stream", side_effect=mock_stream):
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": session_id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        assert "Hello there!" in response.text
        assert "An error occurred" not in response.text


def test_chat_endpoint_does_not_leak_exception_text_to_client(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Regression for CR-05: upstream exceptions must not leak into the SSE wire.

    Patch chat_stream to raise an exception whose ``str()`` contains
    sensitive substrings (an internal URL and a fake API key). The route
    catch-all MUST emit a static, generic message and NOT echo the
    exception text — even key-shaped substrings would be scrubbed by the
    log filter, but the SSE wire goes directly to the client, so the
    response body must contain none of the original exception text.
    """
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    sensitive_url = "https://api.openai.com/v1/internal-secret"
    sensitive_key = "sk-proj-leaked-from-exception-must-not-appear"

    async def boom(message: str, session_id: str) -> AsyncGenerator[StreamEvent]:
        # An async generator must be a generator function — yield once
        # before raising so the iterator can be advanced into the body.
        if False:
            yield ContentEvent(chunk="never", session_id=session_id)
        raise RuntimeError(f"upstream call to {sensitive_url} failed with key {sensitive_key}")

    with patch("app.chat.service.ChatService.chat_stream", side_effect=boom):
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": session_id},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.text

    # The static, generic message must be present.
    assert "Sorry, something went wrong. Please try again." in body

    # None of the exception text — URL, key, or the legacy raw-leak prefix
    # — must appear on the wire.
    assert sensitive_url not in body
    assert sensitive_key not in body
    assert "An error occurred:" not in body

    # The SSE event must be a well-formed ErrorEvent of type=error (stream_error code).
    # Phase 4.7: route-level exceptions emit ErrorEvent(type="error") instead of the
    # old StreamEvent(type="content") so the frontend can route errors correctly.
    data_lines = [line[len("data: ") :] for line in body.strip().split("\n") if line.startswith("data: ")]
    assert len(data_lines) >= 1
    parsed = json.loads(data_lines[-1])
    assert parsed["type"] == "error"
    assert parsed["error_code"] == "stream_error"
    assert parsed["session_id"] == session_id


def test_chat_endpoint_empty_message(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat endpoint rejects empty messages."""
    # Create session first
    session_response = client.post("/api/chat/session", headers=auth_headers)
    session_id = session_response.json()["session_id"]

    response = client.post(
        "/api/chat",
        json={"message": "", "session_id": session_id},
        headers=auth_headers,
    )

    assert response.status_code == 422  # Validation error


def test_retry_endpoint_replays_last_tool_invocation(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /api/chat/retry replays the last tool invocation stored in session metadata.

    Arrange: create a session, inject last_tool_invocation into metadata directly,
    then POST /api/chat/retry and assert 200 + SSE body containing the replay stream's events.
    """
    # Arrange — create a session
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    # Inject last_tool_invocation directly into the session's metadata.
    # The real ChatService stores it when processing a ToolCall chunk;
    # we bypass the full LLM streaming stack in this integration test.
    chat_service = client.app.state.chat_service
    chat_service._metadata[session_id]["last_tool_invocation"] = {
        "tool_name": "search_flights",
        "tool_args": {"origin": "LAX", "destination": "JFK", "departure_date": "2026-06-15", "passengers": 1},
        "tool_call_id": "call_test",
    }

    # Act — retry stream that yields content
    async def mock_retry_stream(message: str, session_id: str) -> AsyncGenerator[StreamEvent]:
        yield ContentEvent(chunk="Retry result here.", session_id=session_id)

    with patch("app.chat.service.ChatService.chat_stream", side_effect=mock_retry_stream):
        response = client.post(
            "/api/chat/retry",
            json={"session_id": session_id},
            headers=auth_headers,
        )

    # Assert
    assert response.status_code == 200
    assert "Retry result here." in response.text


def test_retry_endpoint_returns_404_for_unknown_session(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /api/chat/retry with an unknown session_id returns 404.

    CR-02 same-shape: missing-or-not-owner both produce 404 so a caller
    cannot probe for session existence.
    """
    # Arrange — use a random session id that was never created
    unknown_session_id = "00000000-0000-0000-0000-000000000000"

    # Act
    response = client.post(
        "/api/chat/retry",
        json={"session_id": unknown_session_id},
        headers=auth_headers,
    )

    # Assert
    assert response.status_code == 404


def test_retry_endpoint_returns_404_for_cross_user_session(client: TestClient, auth_headers: dict[str, str]) -> None:
    """User B calling POST /api/chat/retry with user A's session gets 404 (NOT 403).

    CR-02 / T-04.7-04: same-shape 404 prevents a non-owner from probing
    for session existence via status code differences.
    """
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    import app.api.routes.auth as _auth_module  # local import for targeted monkeypatch

    # Arrange — user A (admin) creates a session
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    # Register a second user (user B) in the module-level user store for this test.
    # The _users_db dict is populated at import time from AUTH_USERS; we inject
    # user B directly so get_current_active_user can validate the token.
    hasher = PasswordHash([Argon2Hasher()])
    user_b_name = "user_b_test_cross_user"
    _auth_module._users_db[user_b_name] = _auth_module.UserInDB(
        username=user_b_name,
        hashed_password=hasher.hash("testpw"),
        disabled=False,
    )
    try:
        user_b_token = create_access_token({"sub": user_b_name})
        user_b_headers = {"Authorization": f"Bearer {user_b_token}"}

        # Act — user B tries to retry user A's session
        response = client.post(
            "/api/chat/retry",
            json={"session_id": session_id},
            headers=user_b_headers,
        )

        # Assert — must be 404 (not 403) to avoid leaking session existence
        assert response.status_code == 404
    finally:
        # Clean up user B from the store to avoid polluting other tests
        _auth_module._users_db.pop(user_b_name, None)


def test_retry_endpoint_returns_422_when_no_last_tool_invocation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """POST /api/chat/retry returns 422 when no last_tool_invocation has been stored.

    A fresh session with no prior chat turn has no last_tool_invocation.
    The retry endpoint must surface this as 422 Unprocessable Entity.
    """
    # Arrange — create a fresh session (no chat turn, so no last_tool_invocation)
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    # Act
    response = client.post(
        "/api/chat/retry",
        json={"session_id": session_id},
        headers=auth_headers,
    )

    # Assert
    assert response.status_code == 422
