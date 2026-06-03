"""Unit tests for GET /api/chat/sessions (D-22, D-27).

Pattern: directly seed ``ChatService._metadata`` for two distinct user_ids and
assert the route filters by ``current_user.username``. The auth_headers fixture
issues an admin token (per conftest), so admin should see only its own seeded
sessions — never alice's or bob's.

Phase 5 / Plan 05-04: ``_histories`` retired in favour of the
``ConversationStore`` seam; ``first_message_preview`` is now composed from
PydanticAI :class:`ModelRequest` / :class:`UserPromptPart`.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, UserPromptPart

from app.api.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def test_sessions_returns_401_without_auth(client: TestClient) -> None:
    response = client.get("/api/chat/sessions")
    assert response.status_code == 401


def _reset_chat_service(chat_service: object) -> None:
    """Clear per-session state on the running ChatService (Phase 5 layout)."""
    chat_service._metadata.clear()  # type: ignore[attr-defined]
    chat_service._last_activity.clear()  # type: ignore[attr-defined]
    chat_service._agents.clear()  # type: ignore[attr-defined]
    # The InMemoryConversationStore exposes ``_store`` as the per-session dict;
    # reaching in here keeps the test layer free of the store ABC's async surface.
    store = chat_service._conversation_store  # type: ignore[attr-defined]
    if hasattr(store, "_store"):
        store._store.clear()


def test_user_with_no_sessions_returns_empty_list(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    chat_service = client.app.state.chat_service
    _reset_chat_service(chat_service)

    response = client.get("/api/chat/sessions", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"sessions": []}


def test_user_sees_only_own_sessions(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    chat_service = client.app.state.chat_service
    _reset_chat_service(chat_service)

    chat_service._metadata["session-alice-1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "alice",
        "created_at": datetime.now(UTC).isoformat(),
    }
    chat_service._metadata["session-bob-1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "bob",
        "created_at": datetime.now(UTC).isoformat(),
    }
    # admin (the auth_headers user per conftest) seeds zero sessions —
    # they should see an empty list, NOT alice's or bob's.

    response = client.get("/api/chat/sessions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body == {"sessions": []}


def test_first_message_preview_populated(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """``first_message_preview`` is composed from a stored ``UserPromptPart`` (D-08)."""
    chat_service = client.app.state.chat_service
    _reset_chat_service(chat_service)

    # Seed the conversation store with a single ModelRequest carrying a UserPromptPart
    # — Phase 5 equivalent of Phase 4.7's ``history.add_user_message(...)``.
    store = chat_service._conversation_store
    store._store["s1"] = [
        ModelRequest(parts=[UserPromptPart(content="This is my first chat message about flights")]),
    ]
    chat_service._metadata["s1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "admin",  # match the auth_headers user (per conftest AUTH_USERS)
        "created_at": datetime.now(UTC).isoformat(),
    }

    response = client.get("/api/chat/sessions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 1
    session = body["sessions"][0]
    assert session["session_id"] == "s1"
    assert session["provider"] == "ollama"
    assert session["model"] == "qwen3:4b"
    assert session["first_message_preview"].startswith("This is my first chat")
