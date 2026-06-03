"""Integration tests for ``GET /api/chat/sessions/{session_id}``.

The route returns the user/assistant turns of a session the caller owns so
the Sidebar's "RECENT CHATS" list can re-render a previously-active session
when clicked. Authentication is required and ownership is enforced — both
"missing session" and "not your session" collapse to a 404 to avoid
leaking session existence across users.

Phase 5 / Plan 05-04: history seeding migrates from LangChain
``HumanMessage`` / ``AIMessage`` into the ``ConversationStore``'s
``ModelRequest`` / ``ModelResponse`` parts (PydanticAI native shape).
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.api.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def two_users(client: TestClient) -> Generator[None]:
    """Seed alice + bob into the running EnvUserRepository."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    from app.auth.models import UserInDB
    from app.auth.repository import EnvUserRepository  # noqa: TC001

    hasher = PasswordHash([Argon2Hasher()])
    user_repo: EnvUserRepository = client.app.state.user_repo
    user_repo.add_user(UserInDB(username="alice", hashed_password=hasher.hash("alicepass"), disabled=False))
    user_repo.add_user(UserInDB(username="bob", hashed_password=hasher.hash("bobpass"), disabled=False))
    yield
    user_repo.remove_user("alice")
    user_repo.remove_user("bob")


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_history_returns_401_without_auth(client: TestClient, auth_headers: dict[str, str]) -> None:
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    response = client.get(f"/api/chat/sessions/{session_id}")
    assert response.status_code == 401


def test_get_history_returns_404_for_missing_session(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/chat/sessions/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_get_history_returns_empty_messages_for_freshly_created_session(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    session_response = client.post("/api/chat/session", headers=auth_headers)
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    response = client.get(f"/api/chat/sessions/{session_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:4b"
    assert body["messages"] == []


def test_get_history_returns_user_and_assistant_turns_in_order(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A session with seeded user/assistant messages round-trips faithfully."""
    session_response = client.post("/api/chat/session", headers=auth_headers)
    session_id = session_response.json()["session_id"]

    chat_service = client.app.state.chat_service
    # Phase 5 / Plan 05-04: seed PydanticAI's ModelRequest/ModelResponse parts
    # directly via the InMemoryConversationStore's ``_store`` dict. The empty
    # TextPart simulates a tool-call-only assistant turn; the route must
    # filter it out (Phase 4.7 contract preserved).
    chat_service._conversation_store._store[session_id] = [
        ModelRequest(parts=[UserPromptPart(content="Plan a trip to Tokyo")]),
        ModelResponse(parts=[TextPart(content="Sure — what dates?")]),
        ModelRequest(parts=[UserPromptPart(content="June 1-7")]),
        ModelResponse(parts=[TextPart(content="")]),
    ]

    response = client.get(f"/api/chat/sessions/{session_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == [
        {"role": "user", "content": "Plan a trip to Tokyo"},
        {"role": "assistant", "content": "Sure — what dates?"},
        {"role": "user", "content": "June 1-7"},
    ]


def test_get_history_returns_404_when_user_does_not_own_session(client: TestClient, two_users: None) -> None:
    """Bob must not see Alice's history. 404 on miss preserves the existence
    oracle threat-model parity with DELETE /api/chat/session/{id}.
    """
    del two_users
    alice_headers = _login(client, "alice", "alicepass")
    bob_headers = _login(client, "bob", "bobpass")

    session_response = client.post("/api/chat/session", headers=alice_headers)
    alice_session_id = session_response.json()["session_id"]

    chat_service = client.app.state.chat_service
    chat_service._conversation_store._store[alice_session_id] = [
        ModelRequest(parts=[UserPromptPart(content="alice's secret trip plan")]),
    ]

    # Bob must NOT see alice's history.
    bob_response = client.get(f"/api/chat/sessions/{alice_session_id}", headers=bob_headers)
    assert bob_response.status_code == 404

    # Alice still can.
    alice_response = client.get(f"/api/chat/sessions/{alice_session_id}", headers=alice_headers)
    assert alice_response.status_code == 200
    assert alice_response.json()["messages"] == [
        {"role": "user", "content": "alice's secret trip plan"},
    ]
