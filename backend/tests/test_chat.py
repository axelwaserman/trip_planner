"""Test chat endpoint."""

from collections.abc import AsyncGenerator
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_endpoint_streams_response() -> None:
    """Test chat endpoint returns streaming response."""

    async def mock_stream(message: str, session_id: str | None) -> AsyncGenerator[tuple[str, str]]:
        """Mock async generator for streaming."""
        yield ("Hello", "test-session-123")
        yield (" there!", "test-session-123")

    with patch("app.api.routes.chat.chat_service.chat_stream", side_effect=mock_stream):
        response = client.post(
            "/api/chat",
            json={"message": "Hello"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_chat_endpoint_empty_message() -> None:
    """Test chat endpoint rejects empty messages."""
    response = client.post(
        "/api/chat",
        json={"message": ""},
    )

    assert response.status_code == 422  # Validation error
