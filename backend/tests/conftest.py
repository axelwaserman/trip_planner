"""Shared pytest fixtures for tests.

Phase 6 / Plan 06-04 (D-07) deleted ``EnvUserRepository``; in-memory tests
that drive the FastAPI app via ``TestClient`` swap the user-repo + chat
collaborators with in-memory shims via ``app.dependency_overrides`` and
``app.state``. The override layer takes precedence over the lifespan's
Postgres wiring so the in-memory swap survives ``with TestClient(app):``.
End-to-end Postgres coverage lives in ``tests/integration/db/``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.api.main import app
from app.auth import routes as auth_routes
from app.auth.models import UserInDB
from app.auth.routes import create_access_token
from app.chat import (
    InMemoryConversationRepository,
    InMemoryMessageStore,
)
from app.tools.flight_client import MockFlightAPIClient
from tests.fixtures.users import InMemoryUserRepository

if TYPE_CHECKING:
    from collections.abc import Generator

    from app.chat.repository import ConversationRepository
    from app.chat.store import MessageStore


@pytest.fixture(autouse=True)
def _inmemory_user_repo(monkeypatch: pytest.MonkeyPatch) -> Generator[InMemoryUserRepository]:
    """Override the user-repository dependency with an in-memory shim.

    Phase 6 / Plan 06-04 wires :class:`PostgresUserRepository` into the
    lifespan; in-memory ``TestClient`` tests don't hit a real Postgres, so
    we monkeypatch the lifespan's import-bound ``PostgresUserRepository``
    to a factory that returns an in-memory repo seeded with ``admin``, AND
    register a dependency override at the FastAPI layer for the same repo
    instance. End-to-end Postgres login coverage lives in
    ``tests/integration/db/test_auth_postgres_login.py``.
    """
    from app.auth.repository import _password_hasher

    repo = InMemoryUserRepository()
    repo.add_user(
        UserInDB(
            username="admin",
            hashed_password=_password_hasher.hash("admin"),
            disabled=False,
        ),
    )

    # Swap the lifespan's bound class so ``app.state.user_repo`` ends up as
    # this in-memory repo instead of a PostgresUserRepository.
    from app.api import main as api_main

    monkeypatch.setattr(api_main, "PostgresUserRepository", lambda *_args, **_kwargs: repo)

    async def _inmemory_override() -> InMemoryUserRepository:
        return repo

    previous_override = app.dependency_overrides.get(auth_routes.get_user_repository)
    app.dependency_overrides[auth_routes.get_user_repository] = _inmemory_override
    try:
        yield repo
    finally:
        if previous_override is None:
            del app.dependency_overrides[auth_routes.get_user_repository]
        else:
            app.dependency_overrides[auth_routes.get_user_repository] = previous_override


@pytest.fixture(autouse=True)
def _inmemory_chat_collaborators(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[InMemoryMessageStore, InMemoryConversationRepository]]:
    """Swap chat-service collaborators with in-memory impls during the test.

    Phase 6 / Plan 06-04 wires :class:`PostgresMessageStore` +
    :class:`PostgresConversationRepository` into the lifespan; in-memory
    ``TestClient`` tests don't hit a real Postgres, so we monkeypatch the
    Postgres class constructors at the import surface used by the lifespan
    so they instantiate the in-memory impls instead. The swap reverts on
    teardown via ``monkeypatch``'s autouse cleanup.
    """
    message_store = InMemoryMessageStore()
    conversation_repo = InMemoryConversationRepository()

    # The lifespan imports the symbols once at module load time:
    #   from app.chat import (PostgresConversationRepository, PostgresMessageStore, ...)
    # We swap those module-level references so the lifespan picks up our
    # in-memory impls without us having to override the dependency layer or
    # restart the app. Both monkeypatched factories return the SAME instance
    # every time so per-test state survives the swap.
    from app.api import main as api_main

    monkeypatch.setattr(api_main, "PostgresMessageStore", lambda *_args, **_kwargs: message_store)
    monkeypatch.setattr(api_main, "PostgresConversationRepository", lambda *_args, **_kwargs: conversation_repo)

    # Also override the route-layer placeholder dependencies so any path
    # that resolves them via Depends() — Plan 06-05a's request rewrite will
    # — picks up the same in-memory instances.
    from app.api.routes import routes as api_routes

    async def _msg_store_override() -> MessageStore:
        return message_store

    async def _conv_repo_override() -> ConversationRepository:
        return conversation_repo

    prev_msg_override = app.dependency_overrides.get(api_routes.get_message_store)
    prev_conv_override = app.dependency_overrides.get(api_routes.get_conversation_repo)
    app.dependency_overrides[api_routes.get_message_store] = _msg_store_override
    app.dependency_overrides[api_routes.get_conversation_repo] = _conv_repo_override

    try:
        yield message_store, conversation_repo
    finally:
        if prev_msg_override is None:
            app.dependency_overrides.pop(api_routes.get_message_store, None)
        else:
            app.dependency_overrides[api_routes.get_message_store] = prev_msg_override
        if prev_conv_override is None:
            app.dependency_overrides.pop(api_routes.get_conversation_repo, None)
        else:
            app.dependency_overrides[api_routes.get_conversation_repo] = prev_conv_override


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return HTTP headers with a valid JWT Bearer token for the default admin user.

    Uses the ``admin`` user the autouse ``_inmemory_user_repo`` fixture seeds.
    """
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_flight_client() -> MockFlightAPIClient:
    """Create MockFlightAPIClient for testing.

    Returns:
        MockFlightAPIClient with fixed seed for reproducibility
    """
    return MockFlightAPIClient(seed=42)
