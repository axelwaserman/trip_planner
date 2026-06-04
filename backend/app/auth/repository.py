"""UserRepository — ABC + Postgres-backed implementation.

Phase 6 / Plan 06-04 (D-07): the Phase 4 env-backed user repository is
deleted here. ``PostgresUserRepository`` is the sole concrete implementation
going forward; users are seeded via ``just db-seed`` (Plan 06-06) into the
``user`` table, and the auth route layer talks to the ABC unchanged.

The :class:`UserRepository` ABC's :meth:`get_user` flips to ``async def``
because the SQL lookup is async; :meth:`verify_password` stays sync because
``pwdlib`` is CPU-bound, not I/O. The ``_DUMMY_HASH`` constant-time
enumeration guard (V2 Authentication / threat T-06-04-01) survives — the
auth route's "user not found" branch still calls ``verify_password`` against
``_DUMMY_HASH`` to equalise wall-clock timing between known-and-unknown
usernames. The same module-level ``_password_hasher`` argon2 singleton is
preserved so any pre-existing hashed password remains verifiable.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlmodel import col, select

from app.auth.exceptions import UserNotFoundError
from app.auth.models import UserInDB
from app.db.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


logger = logging.getLogger(__name__)

# Module-level hasher singleton.
# T-4.9.02-A: Must remain Argon2 — changing the hasher constructor would
# invalidate all hashed passwords stored in the ``user`` table.
_password_hasher = PasswordHash([Argon2Hasher()])

# Pre-computed hash used for constant-time comparison when a username is not found.
# Mitigation V2 Authentication / threat T-06-04-01: prevents username enumeration
# via wall-clock timing differences between known-vs-unknown usernames. The auth
# route at ``app/auth/routes.py::login`` calls ``repo.verify_password(plain, _DUMMY_HASH)``
# in the not-found branch so both paths pay the argon2 verify cost.
_DUMMY_HASH: str = _password_hasher.hash("__dummy__")


class UserRepository(ABC):
    """Abstract base class for user persistence backends.

    The auth routes depend on this ABC; concrete implementations
    (Phase 6: :class:`PostgresUserRepository`) are injected via FastAPI's
    dependency override mechanism. The ABC contract is async on the I/O
    operation (``get_user``) and sync on the CPU-bound argon2 verify path
    per CLAUDE.md "all I/O must be ``async def``".
    """

    @abstractmethod
    async def get_user(self, username: str) -> UserInDB:
        """Return UserInDB for *username*.

        Args:
            username: Authentication subject (login name).

        Raises:
            UserNotFoundError: When *username* does not exist in the backend.
        """
        ...

    @abstractmethod
    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if *plain* matches *hashed*."""
        ...


class PostgresUserRepository(UserRepository):
    """Postgres-backed :class:`UserRepository` (D-07; sole impl in Phase 6+).

    Replaces the Phase 4 env-backed repository. ``get_user`` issues a single
    ``SELECT`` against the :class:`User` SQLModel table; the bind parameter
    is fully parameterised (no string formatting), defending against SQL
    injection (threat T-06-04-01 mitigation).

    The store opens its own short transaction per call via the injected
    :class:`async_sessionmaker`; it never holds an :class:`AsyncSession`
    across a request lifetime (06-RESEARCH.md Pitfall 3 / consistent with
    :class:`PostgresMessageStore`).
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_user(self, username: str) -> UserInDB:
        """Look up a user by ``username`` via parameterised SELECT.

        Raises:
            UserNotFoundError: When the row does not exist.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(User).where(col(User.username) == username),
            )
            row = result.scalar_one_or_none()
        if row is None:
            raise UserNotFoundError(username)
        return UserInDB(
            username=row.username,
            hashed_password=row.hashed_password,
            disabled=row.disabled,
        )

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if *plain* matches *hashed* using Argon2."""
        return _password_hasher.verify(plain, hashed)
