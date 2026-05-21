"""Integration test — sessions are partitioned per authenticated user (D-22, D-27).

Two distinct users log in, each owns a session in ``ChatService._metadata``,
and each ``GET /api/chat/sessions`` call MUST return only its caller's
sessions. Closes RESEARCH.md Open Question 5 (RESOLVED).
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from langchain_core.chat_history import InMemoryChatMessageHistory


@pytest.fixture(autouse=True)
def two_users(client: TestClient) -> Generator[None]:
    """Seed alice + bob into the running EnvUserRepository for each test."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    from app.auth.models import UserInDB
    from app.auth.repository import EnvUserRepository

    hasher = PasswordHash([Argon2Hasher()])
    user_repo: EnvUserRepository = client.app.state.user_repo
    user_repo.add_user(UserInDB(username="alice", hashed_password=hasher.hash("alicepass"), disabled=False))
    user_repo.add_user(UserInDB(username="bob", hashed_password=hasher.hash("bobpass"), disabled=False))
    yield
    user_repo.remove_user("alice")
    user_repo.remove_user("bob")


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    from app.api.main import app

    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_two_users_get_independent_session_lists(
    client: TestClient,
) -> None:
    # Arrange — clear chat state, log in as alice + bob
    chat_service = client.app.state.chat_service
    chat_service._histories.clear()
    chat_service._metadata.clear()
    chat_service._last_activity.clear()
    chat_service._bound_providers.clear()

    alice_headers = _login(client, "alice", "alicepass")
    bob_headers = _login(client, "bob", "bobpass")

    # Act 1 — alice's sessions list is initially empty
    r1 = client.get("/api/chat/sessions", headers=alice_headers)
    assert r1.status_code == 200
    assert r1.json() == {"sessions": []}

    # Act 2 — bob's sessions list is initially empty
    r1b = client.get("/api/chat/sessions", headers=bob_headers)
    assert r1b.status_code == 200
    assert r1b.json() == {"sessions": []}

    # Seed one session per user directly via metadata.
    # We bypass the create_session route because that requires a live provider
    # probe; the partition behaviour is the unit-of-test here.
    chat_service._histories["alice-1"] = InMemoryChatMessageHistory()
    chat_service._metadata["alice-1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "alice",
        "created_at": datetime.now(UTC).isoformat(),
    }
    chat_service._histories["bob-1"] = InMemoryChatMessageHistory()
    chat_service._metadata["bob-1"] = {
        "provider": "ollama",
        "model": "qwen3:4b",
        "user_id": "bob",
        "created_at": datetime.now(UTC).isoformat(),
    }

    # Act 3 — alice lists sessions, sees ONLY alice-1
    r2 = client.get("/api/chat/sessions", headers=alice_headers)
    assert r2.status_code == 200
    alice_sessions = r2.json()["sessions"]
    assert len(alice_sessions) == 1
    assert alice_sessions[0]["session_id"] == "alice-1"

    # Act 4 — bob lists sessions, sees ONLY bob-1
    r3 = client.get("/api/chat/sessions", headers=bob_headers)
    assert r3.status_code == 200
    bob_sessions = r3.json()["sessions"]
    assert len(bob_sessions) == 1
    assert bob_sessions[0]["session_id"] == "bob-1"
