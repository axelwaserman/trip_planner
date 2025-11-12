"""Test chat endpoint."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_endpoint_new_session() -> None:
    """Test chat endpoint creates new session and returns response."""
    # Mock the chat service to avoid calling real Ollama
    with patch("app.main.chat_service.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = ("Hello! How can I help you plan your trip?", "test-session-123")

        response = client.post(
            "/api/chat",
            json={"message": "Hello"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "session_id" in data
        assert data["session_id"] == "test-session-123"
        mock_chat.assert_called_once_with("Hello", None)


def test_chat_endpoint_existing_session() -> None:
    """Test chat endpoint with existing session ID."""
    with patch("app.main.chat_service.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = ("I remember our conversation!", "existing-session")

        response = client.post(
            "/api/chat",
            json={"message": "Do you remember me?", "session_id": "existing-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "existing-session"
        mock_chat.assert_called_once_with("Do you remember me?", "existing-session")


def test_chat_endpoint_empty_message() -> None:
    """Test chat endpoint rejects empty messages."""
    response = client.post(
        "/api/chat",
        json={"message": ""},
    )

    assert response.status_code == 422  # Validation error


def test_chat_endpoint_service_error() -> None:
    """Test chat endpoint handles service errors gracefully."""
    with patch("app.main.chat_service.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = Exception("Ollama connection failed")

        response = client.post(
            "/api/chat",
            json={"message": "Hello"},
        )

        assert response.status_code == 500
        assert "Chat service error" in response.json()["detail"]
