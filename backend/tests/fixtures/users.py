"""Test-only in-memory :class:`UserRepository` shim.

Phase 6 / Plan 06-04 deletes the production :class:`EnvUserRepository` and
its ``AUTH_USERS`` env-driven backing dict (D-07). Several integration
tests still need to seed an ``alice`` / ``bob`` pair directly into the
running app for cross-user behaviour assertions (session partitioning,
history ownership 404 shape, delete-by-non-owner). Those tests previously
reached into ``app.state.user_repo.add_user(...)`` against
``EnvUserRepository``.

To keep the in-memory FastAPI ``TestClient`` tests independent of a live
Postgres without smuggling ``EnvUserRepository`` back, these tests now use
:class:`InMemoryUserRepository` — an in-memory subclass of
:class:`UserRepository` (the abstract base that survived Plan 06-04) with a
matching ``async def get_user`` and helper ``add_user`` / ``remove_user``
seeding methods. The end-to-end Postgres login round-trip is locked
separately in ``tests/integration/db/test_auth_postgres_login.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.auth.exceptions import UserNotFoundError
from app.auth.repository import UserRepository, _password_hasher

if TYPE_CHECKING:
    from app.auth.models import UserInDB


class InMemoryUserRepository(UserRepository):
    """In-memory :class:`UserRepository` for FastAPI ``TestClient`` tests.

    Mirrors the deleted :class:`EnvUserRepository`'s ``add_user`` /
    ``remove_user`` test-helper surface so existing cross-user integration
    tests can seed alice/bob without standing up a Postgres test fixture.
    The async ``get_user`` matches the new ABC contract verbatim.
    """

    def __init__(self) -> None:
        self._users: dict[str, UserInDB] = {}

    async def get_user(self, username: str) -> UserInDB:
        """Return the seeded user, or raise :class:`UserNotFoundError`."""
        user = self._users.get(username)
        if user is None:
            raise UserNotFoundError(username)
        return user

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Argon2 verify via the canonical shared :data:`_password_hasher`."""
        return _password_hasher.verify(plain, hashed)

    def add_user(self, user: UserInDB) -> None:
        """Seed a user — for testing and local dev only."""
        self._users[user.username] = user

    def remove_user(self, username: str) -> None:
        """Remove a seeded user — for test teardown only."""
        self._users.pop(username, None)
