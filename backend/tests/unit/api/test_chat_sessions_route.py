"""Unit tests for GET /api/chat/sessions (D-22, D-27).

Pattern: directly seed ``ChatService._metadata`` for two distinct user_ids and
assert the route filters by ``current_user.username``. The auth_headers fixture
issues an admin token (per conftest), so admin should see only its own seeded
sessions — never alice's or bob's.

Phase 6 / Plan 06-04: ``_conversation_store`` retired in favour of the
D-05/D-06 split; the legacy ``_store`` peek is gone — ``MessageStore.first_user_message_preview``
is the canonical CR-04 fix and lives on the ABC. Session ids are UUID-strings
because the new store keys are :class:`uuid.UUID` (squash-merge boundary
documented in the plan's Constraints section).
"""

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
    """Clear per-session state on the running ChatService (Phase 6 layout).

    Plan 06-04: the in-memory message store exposes ``_store`` as a per-UUID
    dict; we clear that directly so the test layer doesn't have to walk the
    ABC's async surface for setup.
    """
    chat_service._metadata.clear()  # type: ignore[attr-defined]
    chat_service._last_activity.clear()  # type: ignore[attr-defined]
    chat_service._agents.clear()  # type: ignore[attr-defined]
    store = chat_service._message_store  # type: ignore[attr-defined]
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

    alice_session_id = str(uuid4())
    bob_session_id = str(uuid4())
    chat_service._metadata[alice_session_id] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "alice",
        "created_at": datetime.now(UTC).isoformat(),
    }
    chat_service._metadata[bob_session_id] = {
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
    """``first_message_preview`` flows through ``MessageStore.first_user_message_preview`` (CR-04 fix)."""
    chat_service = client.app.state.chat_service
    _reset_chat_service(chat_service)

    # Seed the message store with a single ModelRequest carrying a UserPromptPart
    # via the in-memory impl's ``_store`` dict (UUID-keyed in Phase 6).
    session_uuid = uuid4()
    session_id = str(session_uuid)
    store = chat_service._message_store
    store._store[session_uuid] = [
        ModelRequest(parts=[UserPromptPart(content="This is my first chat message about flights")]),
    ]
    chat_service._metadata[session_id] = {
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
    assert session["session_id"] == session_id
    assert session["provider"] == "ollama"
    assert session["model"] == "qwen3:4b"
    assert session["first_message_preview"].startswith("This is my first chat")
    # Confirm the seeded UUID is well-formed (catches the str-vs-UUID drift
    # documented in the plan's squash-merge boundary).
    UUID(session["session_id"])
