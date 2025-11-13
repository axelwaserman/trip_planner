"""Test chat endpoint."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.domain.chat import StreamEvent
from app.main import app


@pytest.fixture
def client():
    """Create test client with lifespan."""
    with TestClient(app) as c:
        yield c


def test_chat_endpoint_requires_session_id(client: TestClient) -> None:
    """Test chat endpoint requires session_id."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello"},
    )
    assert response.status_code == 400
    assert "session_id is required" in response.json()["detail"]


def test_chat_endpoint_rejects_invalid_session(client: TestClient) -> None:
    """Test chat endpoint rejects invalid session."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello", "session_id": "invalid-session"},
    )
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


def test_chat_endpoint_streams_response(client: TestClient) -> None:
    """Test chat endpoint returns streaming response."""

    async def mock_stream(
        message: str, session_id: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """Mock async generator for streaming."""
        yield StreamEvent(
            event_type="content",
            content="Hello there!",
            session_id=session_id,
            metadata=None,
        )

    # Create a session first
    session_response = client.post("/api/chat/session")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    # Patch the ChatService.chat_stream method
    with patch("app.chat.ChatService.chat_stream", side_effect=mock_stream):
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": session_id},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_chat_endpoint_empty_message(client: TestClient) -> None:
    """Test chat endpoint rejects empty messages."""
    # Create session first
    session_response = client.post("/api/chat/session")
    session_id = session_response.json()["session_id"]

    response = client.post(
        "/api/chat",
        json={"message": "", "session_id": session_id},
    )

    assert response.status_code == 422  # Validation error
