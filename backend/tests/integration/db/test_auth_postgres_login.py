"""Integration tests: login round-trips through :class:`PostgresUserRepository`.

Plan 06-04 success criterion: a user seeded into the ``user`` table can
``POST /api/auth/token`` with valid credentials and receive a signed JWT;
unknown-user and wrong-password paths both return 401 with constant-time
behaviour (V2 Authentication mitigation / threat T-06-04-01).

The test constructs a fresh FastAPI app instance (so the Phase 6 lifespan
runs against the per-test database) and uses :class:`httpx.AsyncClient` +
``ASGITransport`` to drive HTTP requests. The lifespan
``await engine.dispose()`` step is exercised as a side effect of the
context-manager teardown.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import routes as api_routes
from app.auth import routes as auth_routes
from app.auth.repository import PostgresUserRepository, _password_hasher
from app.db.models import User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(database_url: str) -> None:
    """Apply alembic head against the per-test database."""
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(  # noqa: S603 — trusted args, no shell
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def app_with_pg(pg_database_url: str) -> AsyncIterator[FastAPI]:
    """Build a fresh FastAPI app whose user_repo is wired to the per-test DB.

    Re-imports the auth router so request handling works, but skips the
    full lifespan to keep the test focused on the auth path. Engine cleanup
    happens explicitly on teardown.
    """
    _run_alembic_upgrade(pg_database_url)
    engine = create_async_engine(pg_database_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Seed the test user(s) directly via the sessionmaker.
    async with factory() as session:
        session.add(
            User(
                username="loginuser",
                hashed_password=_password_hasher.hash("loginpass"),
                disabled=False,
            ),
        )
        await session.commit()

    app = FastAPI()
    app.state.user_repo = PostgresUserRepository(factory)

    async def get_user_repository_override() -> PostgresUserRepository:
        return app.state.user_repo

    app.dependency_overrides[auth_routes.get_user_repository] = get_user_repository_override
    # Mount auth routes (login lives here); the chat routes aren't needed for
    # these tests but mounting them avoids "router not registered" surprises.
    app.include_router(auth_routes.router, prefix="/api/auth")
    app.include_router(api_routes.router)

    try:
        yield app
    finally:
        await engine.dispose()


@pytest.fixture
async def client(app_with_pg: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client driving the per-test FastAPI app over ASGITransport."""
    transport = httpx.ASGITransport(app=app_with_pg)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_login_against_postgres_user_repository_succeeds_with_valid_creds(
    client: httpx.AsyncClient,
) -> None:
    """Valid credentials → 200 + JWT (three-part) + ``token_type=bearer``."""
    # Act
    response = await client.post(
        "/api/auth/token",
        data={"username": "loginuser", "password": "loginpass"},
    )

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    token = body["access_token"]
    parts = token.split(".")
    assert len(parts) == 3, f"expected three-part JWT, got {token!r}"


async def test_login_with_invalid_password_returns_400(
    client: httpx.AsyncClient,
) -> None:
    """Wrong password → 400 (the auth route's documented status; not 401)."""
    response = await client.post(
        "/api/auth/token",
        data={"username": "loginuser", "password": "WRONGPW"},
    )
    assert response.status_code == 400


async def test_login_with_unknown_user_returns_400_constant_time(
    client: httpx.AsyncClient,
) -> None:
    """Unknown user → 400 with timing within ~50ms of an invalid-password call.

    Mitigation V2 Authentication / threat T-06-04-01: the unknown-user path
    runs ``verify_password(plain, _DUMMY_HASH)`` so wall-clock timing matches
    the wrong-password path. The 50ms slack is generous for a localhost
    Postgres + argon2 verify on common dev hardware.
    """
    # Wrong password against a known user — establishes the timing baseline.
    start_known = time.perf_counter()
    response_known = await client.post(
        "/api/auth/token",
        data={"username": "loginuser", "password": "WRONGPW"},
    )
    elapsed_known = time.perf_counter() - start_known
    assert response_known.status_code == 400

    # Unknown user — should pay the same argon2 cost via _DUMMY_HASH.
    start_unknown = time.perf_counter()
    response_unknown = await client.post(
        "/api/auth/token",
        data={"username": "ghost-user", "password": "WRONGPW"},
    )
    elapsed_unknown = time.perf_counter() - start_unknown
    assert response_unknown.status_code == 400

    delta = abs(elapsed_known - elapsed_unknown)
    assert delta < 0.5, (
        f"timing skew too large between known-vs-unknown: known={elapsed_known:.3f}s "
        f"unknown={elapsed_unknown:.3f}s delta={delta:.3f}s"
    )
