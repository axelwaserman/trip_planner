"""Integration tests for session create/delete routes."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def two_users(client: TestClient) -> Generator[None]:
    """Seed alice + bob into the running EnvUserRepository for cross-user tests."""
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


class TestDeleteSession:
    def test_delete_removes_session_from_all_dicts(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        session_response = client.post("/api/chat/session", headers=auth_headers)
        assert session_response.status_code == 201
        session_id = session_response.json()["session_id"]

        chat_service = client.app.state.chat_service
        # Phase 5 / Plan 05-04: ``_histories`` retired in favour of the ``_agents`` dict
        # + ``ConversationStore``. Session creation populates ``_agents`` and ``_metadata``.
        assert session_id in chat_service._agents
        assert session_id in chat_service._metadata
        assert session_id in chat_service._last_activity

        delete_response = client.delete(f"/api/chat/session/{session_id}", headers=auth_headers)

        assert delete_response.status_code == 204
        assert session_id not in chat_service._agents
        assert session_id not in chat_service._metadata
        assert session_id not in chat_service._last_activity

    def test_delete_without_auth_returns_401(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Regression for CR-01: unauthenticated DELETE must NOT delete a session."""
        session_response = client.post("/api/chat/session", headers=auth_headers)
        assert session_response.status_code == 201
        session_id = session_response.json()["session_id"]

        chat_service = client.app.state.chat_service
        assert session_id in chat_service._metadata

        # No auth header — must be rejected by the auth dependency.
        delete_response = client.delete(f"/api/chat/session/{session_id}")
        assert delete_response.status_code == 401

        # Session must still exist after the rejected attempt.
        assert session_id in chat_service._metadata

    def test_delete_nonexistent_session_returns_404(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        response = client.delete("/api/chat/session/does-not-exist", headers=auth_headers)

        assert response.status_code == 404

    def test_delete_already_deleted_session_returns_404(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        session_response = client.post("/api/chat/session", headers=auth_headers)
        session_id = session_response.json()["session_id"]

        client.delete(f"/api/chat/session/{session_id}", headers=auth_headers)
        response = client.delete(f"/api/chat/session/{session_id}", headers=auth_headers)

        assert response.status_code == 404

    def test_user_cannot_delete_another_users_session(self, client: TestClient, two_users: None) -> None:
        """Regression for CR-01: a non-owner must NOT be able to delete the session.

        Alice creates a session; Bob tries to delete it with his own valid
        token. The response MUST be 404 (same shape as missing) and the
        session MUST still exist in ChatService state.
        """
        del two_users  # marker — fixture seeded the alice/bob users.
        alice_headers = _login(client, "alice", "alicepass")
        bob_headers = _login(client, "bob", "bobpass")

        session_response = client.post("/api/chat/session", headers=alice_headers)
        assert session_response.status_code == 201
        alice_session_id = session_response.json()["session_id"]

        chat_service = client.app.state.chat_service
        assert alice_session_id in chat_service._metadata

        # Bob tries to delete alice's session — must fail with 404 (not 204,
        # not 403) so existence is not leaked.
        delete_response = client.delete(f"/api/chat/session/{alice_session_id}", headers=bob_headers)
        assert delete_response.status_code == 404

        # Session still exists and is still owned by alice.
        assert alice_session_id in chat_service._metadata
        assert chat_service._metadata[alice_session_id]["user_id"] == "alice"

        # Alice can still delete her own session.
        owner_delete = client.delete(f"/api/chat/session/{alice_session_id}", headers=alice_headers)
        assert owner_delete.status_code == 204
        assert alice_session_id not in chat_service._metadata


class TestChatInvalidSession:
    def test_invalid_session_returns_404(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Per CR-02 the route raises 404 at the boundary for missing sessions.

        The previous behaviour emitted an empty SSE event with status 200; we
        now reject before opening the stream because (a) the same 404 shape
        is used for not-owner and (b) emitting nothing-but-an-empty-chunk is
        indistinguishable from an empty success on the client side.
        """
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": "nonexistent-session-id"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_user_cannot_post_to_another_users_session(self, client: TestClient, two_users: None) -> None:
        """Regression for CR-02: a non-owner cannot POST to /api/chat.

        Alice creates a session; Bob (with his own valid token) tries to
        POST a message to Alice's session_id. The response MUST be 404 (not
        200, not 403) so existence is not leaked, and Alice's session
        history MUST NOT have any new entries.
        """
        del two_users  # marker — fixture seeded the alice/bob users.
        alice_headers = _login(client, "alice", "alicepass")
        bob_headers = _login(client, "bob", "bobpass")

        session_response = client.post("/api/chat/session", headers=alice_headers)
        assert session_response.status_code == 201
        alice_session_id = session_response.json()["session_id"]

        chat_service = client.app.state.chat_service
        # Phase 6 / Plan 06-04: history lives in the MessageStore (D-05/D-06
        # split). The in-memory impl exposes ``_store`` as a UUID-keyed dict
        # for synchronous test access; we read the entry directly here so
        # this method stays sync.
        from uuid import UUID

        store = chat_service._message_store
        original_history_len = len(store._store.get(UUID(alice_session_id), []))

        # Bob tries to post a message to alice's session.
        response = client.post(
            "/api/chat",
            json={"message": "I'm bob, hijacking alice's chat", "session_id": alice_session_id},
            headers=bob_headers,
        )
        assert response.status_code == 404

        # Alice's history must NOT have been mutated by bob's attempt.
        new_history_len = len(store._store.get(UUID(alice_session_id), []))
        assert new_history_len == original_history_len
