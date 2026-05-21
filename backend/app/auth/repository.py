"""UserRepository — ABC + EnvUserRepository implementation.

The UserRepository ABC defines the interface that auth routes depend on.
EnvUserRepository implements it by loading users from the AUTH_USERS environment
variable at construction time — the same logic previously inlined in auth.py.

Phase 5 replaces EnvUserRepository with PostgresUserRepository by overriding
the get_user_repository FastAPI dependency in the lifespan — zero route changes
will be needed at that point.
"""

import logging
import os
from abc import ABC, abstractmethod

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.auth.exceptions import UserNotFoundError
from app.auth.models import UserInDB
from app.config import settings

logger = logging.getLogger(__name__)

# Module-level hasher singleton used by EnvUserRepository.verify_password.
# T-4.9.02-A: Must remain Argon2 — changing the hasher constructor would
# invalidate all hashed passwords stored in AUTH_USERS.
_password_hasher = PasswordHash([Argon2Hasher()])

# Pre-computed hash used for constant-time comparison when a username is not found.
# This prevents username enumeration via response-time differences.
_DUMMY_HASH: str = _password_hasher.hash("__dummy__")


class UserRepository(ABC):
    """Abstract base class for user persistence backends.

    The auth routes depend on this ABC; concrete implementations
    (EnvUserRepository, future PostgresUserRepository) are injected via
    FastAPI's dependency override mechanism.
    """

    @abstractmethod
    def get_user(self, username: str) -> UserInDB:
        """Return UserInDB for *username*.

        Raises:
            UserNotFoundError: When *username* does not exist.
        """
        ...

    @abstractmethod
    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if *plain* matches *hashed*."""
        ...


class EnvUserRepository(UserRepository):
    """UserRepository backed by the AUTH_USERS environment variable.

    Loads users once at construction time. Intended as the Phase 4.x user
    source; replaced by PostgresUserRepository in Phase 5.

    AUTH_USERS format: ``user1:pass1,user2:pass2``
    Falls back to ``admin:admin`` when the variable is absent.
    Malformed entries (missing colon, empty username/password) are skipped.
    """

    def __init__(self) -> None:
        self._users: dict[str, UserInDB] = _load_users_from_env()

    def get_user(self, username: str) -> UserInDB:
        """Return UserInDB for *username*.

        Raises:
            UserNotFoundError: When *username* does not exist.
        """
        user = self._users.get(username)
        if user is None:
            raise UserNotFoundError(username)
        return user

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True if *plain* matches *hashed* using Argon2."""
        return _password_hasher.verify(plain, hashed)


def _load_users_from_env() -> dict[str, UserInDB]:
    """Build the in-memory user dict from the AUTH_USERS environment variable.

    This is an internal helper; callers should use EnvUserRepository instead.
    """
    raw = os.environ.get("AUTH_USERS", settings.auth_users)
    users: dict[str, UserInDB] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            logger.warning("Skipping malformed AUTH_USERS entry (no colon): %r", entry)
            continue
        username, _, password = entry.partition(":")
        username = username.strip()
        password = password.strip()
        if not username or not password:
            logger.warning("Skipping AUTH_USERS entry with empty username or password.")
            continue
        users[username] = UserInDB(
            username=username,
            hashed_password=_password_hasher.hash(password),
            disabled=False,
        )
    return users
