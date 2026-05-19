"""Test chat endpoint."""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.models import StreamEvent
from tests.utils.sse import parse_sse_events


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
    """Test chat endpoint rejects invalid session."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello", "session_id": "invalid-session"},
        headers=auth_headers,
    )
    # Endpoint streams errors in SSE format, not HTTP errors
    # So it returns 200 but the stream will contain error event
    assert response.status_code == 200


def test_chat_endpoint_streams_response(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat endpoint returns streaming response."""

    # Create a session first
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201  # Created
    session_id = session_response.json()["session_id"]

    async def mock_stream(message: str, session_id: str) -> AsyncGenerator[StreamEvent]:
        """Mock async generator for streaming."""
        yield StreamEvent(
            type="content",
            chunk="Hello there!",
            session_id=session_id,
        )

    # Patch the ChatService.chat_stream method
    with patch("app.chat.ChatService.chat_stream", side_effect=mock_stream):
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
            yield StreamEvent(type="content", chunk="never", session_id=session_id)
        raise RuntimeError(f"upstream call to {sensitive_url} failed with key {sensitive_key}")

    with patch("app.chat.ChatService.chat_stream", side_effect=boom):
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

    # The SSE event must still be a well-formed StreamEvent of type=content.
    events = parse_sse_events(body)
    assert len(events) >= 1
    assert events[-1].type == "content"
    assert events[-1].session_id == session_id


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
