"""Shared pytest fixtures for tests.

Phase 6 / Plan 06-04 (D-07) deleted ``EnvUserRepository``; in-memory tests
that drive the FastAPI app via ``TestClient`` now swap
``app.state.user_repo`` with an :class:`InMemoryUserRepository` seeded with
the ``admin`` user the ``auth_headers`` JWT identifies. End-to-end Postgres
login round-trip coverage lives in
``tests/integration/db/test_auth_postgres_login.py``.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.api.main import app
from app.auth.models import UserInDB
from app.auth.routes import create_access_token
from app.tools.flight_client import MockFlightAPIClient
from tests.fixtures.users import InMemoryUserRepository


@pytest.fixture(autouse=True)
def _inmemory_user_repo() -> Generator[InMemoryUserRepository]:
    """Swap ``app.state.user_repo`` with an in-memory repo seeded with ``admin``.

    Phase 6 / Plan 06-04 makes ``app.state.user_repo`` a
    :class:`PostgresUserRepository` at lifespan startup; the in-memory
    FastAPI ``TestClient`` tests don't run against a real Postgres, so we
    install a simple in-memory shim during test setup. The override is
    reverted on teardown so suites that DO require the live Postgres path
    (the new ``tests/integration/db/test_auth_postgres_login.py``)
    construct their own app instance.
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

    previous_repo = getattr(app.state, "user_repo", None)
    app.state.user_repo = repo
    try:
        yield repo
    finally:
        if previous_repo is None:
            del app.state.user_repo
        else:
            app.state.user_repo = previous_repo


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return HTTP headers with a valid JWT Bearer token for the default admin user.

    Uses the ``admin`` user the autouse ``_inmemory_user_repo`` fixture seeds
    into ``app.state.user_repo``.
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
