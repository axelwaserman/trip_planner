"""Integration test — sessions are partitioned per authenticated user (D-22, D-27).

Two distinct users log in, each owns a session in ``ChatService._metadata``,
and each ``GET /api/chat/sessions`` call MUST return only its caller's
sessions. Closes RESEARCH.md Open Question 5 (RESOLVED).

Phase 5 / Plan 05-04: ``_histories`` and ``_bound_providers`` retired in
favour of ``_agents`` + the ``ConversationStore`` seam. The per-user
partition behaviour is identical; only the seeding shape changes.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def two_users(client: TestClient) -> Generator[None]:
    """Seed alice + bob into the in-memory test user repo for each test.

    Phase 6 / Plan 06-04 (D-07): cross-user behaviour assertions still hit
    the in-memory FastAPI ``TestClient`` route layer; the conftest's autouse
    ``_inmemory_user_repo`` fixture installs an
    :class:`InMemoryUserRepository` on ``app.state.user_repo`` for this.
    """
    from app.auth.models import UserInDB
    from app.auth.repository import _password_hasher
    from tests.fixtures.users import InMemoryUserRepository

    user_repo: InMemoryUserRepository = client.app.state.user_repo
    user_repo.add_user(UserInDB(username="alice", hashed_password=_password_hasher.hash("alicepass"), disabled=False))
    user_repo.add_user(UserInDB(username="bob", hashed_password=_password_hasher.hash("bobpass"), disabled=False))
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
    chat_service._metadata.clear()
    chat_service._last_activity.clear()
    chat_service._agents.clear()

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
    # Phase 6 / Plan 06-04: session ids must be UUID-strings — the new
    # MessageStore.first_user_message_preview takes a UUID so opaque ids
    # like "alice-1" no longer parse.
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

    # Act 3 — alice lists sessions, sees ONLY her own
    r2 = client.get("/api/chat/sessions", headers=alice_headers)
    assert r2.status_code == 200
    alice_sessions = r2.json()["sessions"]
    assert len(alice_sessions) == 1
    assert alice_sessions[0]["session_id"] == alice_session_id

    # Act 4 — bob lists sessions, sees ONLY his own
    r3 = client.get("/api/chat/sessions", headers=bob_headers)
    assert r3.status_code == 200
    bob_sessions = r3.json()["sessions"]
    assert len(bob_sessions) == 1
    assert bob_sessions[0]["session_id"] == bob_session_id
