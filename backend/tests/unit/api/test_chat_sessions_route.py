"""Unit tests for GET /api/chat/sessions (D-22, D-27).

Pattern: directly seed ``ChatService._metadata`` for two distinct user_ids and
assert the route filters by ``current_user.username``. The auth_headers fixture
issues an admin token (per conftest), so admin should see only its own seeded
sessions — never alice's or bob's.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from langchain_core.chat_history import InMemoryChatMessageHistory

from app.api.main import app

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def test_sessions_returns_401_without_auth(client: TestClient) -> None:
    response = client.get("/api/chat/sessions")
    assert response.status_code == 401


def test_user_with_no_sessions_returns_empty_list(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    # Arrange — clear all sessions so admin sees nothing
    chat_service = client.app.state.chat_service
    chat_service._histories.clear()
    chat_service._metadata.clear()
    chat_service._last_activity.clear()
    chat_service._bound_providers.clear()

    # Act
    response = client.get("/api/chat/sessions", headers=auth_headers)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"sessions": []}


def test_user_sees_only_own_sessions(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    # Arrange — seed sessions for two different users directly in metadata
    chat_service = client.app.state.chat_service
    chat_service._histories.clear()
    chat_service._metadata.clear()
    chat_service._last_activity.clear()
    chat_service._bound_providers.clear()

    chat_service._histories["session-alice-1"] = InMemoryChatMessageHistory()
    chat_service._histories["session-alice-1"].add_user_message("Hi alice")
    chat_service._metadata["session-alice-1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "alice",
        "created_at": datetime.now(UTC).isoformat(),
    }
    chat_service._histories["session-bob-1"] = InMemoryChatMessageHistory()
    chat_service._histories["session-bob-1"].add_user_message("Hi bob")
    chat_service._metadata["session-bob-1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "bob",
        "created_at": datetime.now(UTC).isoformat(),
    }
    # admin (the auth_headers user per conftest) seeds zero sessions —
    # they should see an empty list, NOT alice's or bob's.

    # Act
    response = client.get("/api/chat/sessions", headers=auth_headers)

    # Assert — admin sees neither alice nor bob's sessions
    assert response.status_code == 200
    body = response.json()
    assert body == {"sessions": []}


def test_first_message_preview_populated(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    # Arrange — seed an admin session with a HumanMessage
    chat_service = client.app.state.chat_service
    chat_service._histories.clear()
    chat_service._metadata.clear()
    chat_service._last_activity.clear()
    chat_service._bound_providers.clear()

    history = InMemoryChatMessageHistory()
    history.add_user_message("This is my first chat message about flights")
    chat_service._histories["s1"] = history
    chat_service._metadata["s1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "admin",  # match the auth_headers user (per conftest AUTH_USERS)
        "created_at": datetime.now(UTC).isoformat(),
    }

    # Act
    response = client.get("/api/chat/sessions", headers=auth_headers)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 1
    session = body["sessions"][0]
    assert session["session_id"] == "s1"
    assert session["provider"] == "ollama"
    assert session["model"] == "qwen3:4b"
    assert session["first_message_preview"].startswith("This is my first chat")
