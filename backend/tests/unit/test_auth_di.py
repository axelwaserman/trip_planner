"""Unit tests for DI injection of UserRepository into get_current_user.

TDD RED phase: These tests verify that get_current_user uses the injected
UserRepository rather than the module-global _users_db dict.
They will fail until Task 2 updates the auth route to accept the DI parameter.
"""

import pytest
from fastapi import HTTPException

from app.auth.exceptions import UserNotFoundError
from app.auth.models import UserInDB
from app.auth.repository import UserRepository
from app.auth.routes import create_access_token, get_current_user, get_user_repository

# ---------------------------------------------------------------------------
# Stub implementation of UserRepository Protocol
# ---------------------------------------------------------------------------


class _AlwaysNoneRepo(UserRepository):
    """Stub UserRepository that always raises UserNotFoundError from get_user."""

    async def get_user(self, username: str) -> UserInDB:
        raise UserNotFoundError(username)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return False


class _KnownUserRepo(UserRepository):
    """Stub UserRepository that returns a fixed user for username 'alice'."""

    async def get_user(self, username: str) -> UserInDB:
        if username == "alice":
            return UserInDB(
                username="alice",
                hashed_password="$argon2id$v=19$m=65536,t=2,p=1$fakehash",
                disabled=False,
            )
        raise UserNotFoundError(username)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return plain == "secret"


# ---------------------------------------------------------------------------
# get_user_repository placeholder behaviour
# ---------------------------------------------------------------------------


def test_get_user_repository_placeholder_raises_runtime_error() -> None:
    """get_user_repository raises RuntimeError when no override is configured.

    This ensures unauthenticated access is impossible if the lifespan override
    is accidentally omitted (T-4.9.02-B mitigation).
    """
    with pytest.raises(RuntimeError, match="not configured"):
        get_user_repository()


# ---------------------------------------------------------------------------
# get_current_user uses injected repo
# ---------------------------------------------------------------------------


async def test_get_current_user_rejects_missing_user() -> None:
    """get_current_user raises 401 when the injected repo raises UserNotFoundError.

    Arrange: A stub repo that always raises UserNotFoundError; a valid JWT for "ghost".
    Act: Call get_current_user(token, repo=_AlwaysNoneRepo()).
    Assert: HTTPException with status_code=401 is raised.
    """
    token = create_access_token({"sub": "ghost"})
    repo = _AlwaysNoneRepo()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token, repo)
    assert exc_info.value.status_code == 401


async def test_get_current_user_accepts_valid_token() -> None:
    """get_current_user returns the User when the injected repo finds the username.

    Arrange: A stub repo that returns UserInDB for "alice"; a valid JWT for "alice".
    Act: Call get_current_user(token, repo=_KnownUserRepo()).
    Assert: Returns a User object with username="alice".
    """
    token = create_access_token({"sub": "alice"})
    repo = _KnownUserRepo()
    user = await get_current_user(token, repo)
    assert user.username == "alice"
