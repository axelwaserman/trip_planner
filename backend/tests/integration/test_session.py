"""Integration tests for session create/delete routes."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestDeleteSession:
    def test_delete_removes_session_from_all_dicts(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        session_response = client.post("/api/chat/session", headers=auth_headers)
        assert session_response.status_code == 201
        session_id = session_response.json()["session_id"]

        chat_service = client.app.state.chat_service
        assert session_id in chat_service._histories
        assert session_id in chat_service._metadata
        assert session_id in chat_service._last_activity

        delete_response = client.delete(f"/api/chat/session/{session_id}")

        assert delete_response.status_code == 204
        assert session_id not in chat_service._histories
        assert session_id not in chat_service._metadata
        assert session_id not in chat_service._last_activity

    def test_delete_nonexistent_session_returns_404(self, client: TestClient) -> None:
        response = client.delete("/api/chat/session/does-not-exist")

        assert response.status_code == 404

    def test_delete_already_deleted_session_returns_404(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        session_response = client.post("/api/chat/session", headers=auth_headers)
        session_id = session_response.json()["session_id"]

        client.delete(f"/api/chat/session/{session_id}")
        response = client.delete(f"/api/chat/session/{session_id}")

        assert response.status_code == 404


class TestChatInvalidSession:
    def test_invalid_session_streams_empty_error_event(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": "nonexistent-session-id"},
            headers=auth_headers,
        )

        assert response.status_code == 200

        data_lines = [line for line in response.text.strip().split("\n") if line.startswith("data: ")]
        assert len(data_lines) >= 1

        event = json.loads(data_lines[0][len("data: ") :])
        assert event["type"] == "content"
        assert event["chunk"] == ""
        assert event["session_id"] == "nonexistent-session-id"
