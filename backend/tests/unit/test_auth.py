"""Unit tests for auth module — JWT + password helpers."""

from datetime import timedelta

import pytest

from app.auth.repository import EnvUserRepository
from app.auth.routes import (
    create_access_token,
    get_current_active_user,
    get_current_user,
)

# ---------------------------------------------------------------------------
# EnvUserRepository — user loading (replaces load_users_from_env tests)
# ---------------------------------------------------------------------------


def test_load_users_from_env_parses_single_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parses a single user:pass pair correctly."""
    monkeypatch.setenv("AUTH_USERS", "alice:secret")
    repo = EnvUserRepository()
    user = repo.get_user("alice")
    # hashed password must NOT be the plain password
    assert user.hashed_password != "secret"


def test_load_users_from_env_parses_multiple_users(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parses comma-separated user:pass pairs."""
    monkeypatch.setenv("AUTH_USERS", "alice:secret,bob:hunter2")
    # We test by looking up both users — get_user raises UserNotFoundError if absent.
    repo = EnvUserRepository()
    assert repo.get_user("alice").username == "alice"
    assert repo.get_user("bob").username == "bob"


def test_load_users_from_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to admin:admin when AUTH_USERS is not set."""
    monkeypatch.delenv("AUTH_USERS", raising=False)
    repo = EnvUserRepository()
    assert repo.get_user("admin").username == "admin"


def test_load_users_from_env_ignores_malformed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skips entries that don't have exactly one colon."""
    from app.auth.exceptions import UserNotFoundError

    monkeypatch.setenv("AUTH_USERS", "alice:secret,badentry,bob:hunter2")
    repo = EnvUserRepository()
    assert repo.get_user("alice").username == "alice"
    assert repo.get_user("bob").username == "bob"
    with pytest.raises(UserNotFoundError):
        repo.get_user("badentry")


# ---------------------------------------------------------------------------
# EnvUserRepository — verify_password
# ---------------------------------------------------------------------------


def test_verify_password_returns_true_for_correct_password() -> None:
    """verify_password succeeds when the plain password matches the hash."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    repo = EnvUserRepository()
    ph = PasswordHash([Argon2Hasher()])
    hashed = ph.hash("mypassword")
    assert repo.verify_password("mypassword", hashed) is True


def test_verify_password_returns_false_for_wrong_password() -> None:
    """verify_password fails when the plain password does not match the hash."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    repo = EnvUserRepository()
    ph = PasswordHash([Argon2Hasher()])
    hashed = ph.hash("correct")
    assert repo.verify_password("wrong", hashed) is False


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------


def test_create_access_token_returns_non_empty_string() -> None:
    """Token creation returns a non-empty string."""
    token = create_access_token({"sub": "testuser"})
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_includes_subject() -> None:
    """Token can be decoded and includes the expected subject claim."""
    import jwt

    from app.config import settings

    token = create_access_token({"sub": "alice"})
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == "alice"


def test_create_access_token_respects_custom_expiry() -> None:
    """Token expiry can be overridden."""
    import time

    import jwt

    from app.config import settings

    token = create_access_token({"sub": "alice"}, expires_delta=timedelta(seconds=5))
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    # exp should be within ~10 seconds of now
    assert abs(payload["exp"] - (time.time() + 5)) < 10


# ---------------------------------------------------------------------------
# get_current_user — async dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_invalid_token() -> None:
    """get_current_user raises HTTP 401 when the token is garbage."""
    from fastapi import HTTPException

    from app.auth.exceptions import UserNotFoundError
    from app.auth.models import UserInDB
    from app.auth.repository import UserRepository

    class _NeverFindsUser(UserRepository):
        def get_user(self, username: str) -> UserInDB:
            raise UserNotFoundError(username)

        def verify_password(self, plain: str, hashed: str) -> bool:
            return False

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("not.a.valid.token", _NeverFindsUser())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_unknown_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_current_user raises HTTP 401 when the username is not in the store."""
    from fastapi import HTTPException

    from app.auth.exceptions import UserNotFoundError
    from app.auth.models import UserInDB
    from app.auth.repository import UserRepository

    class _NeverFindsUser(UserRepository):
        def get_user(self, username: str) -> UserInDB:
            raise UserNotFoundError(username)

        def verify_password(self, plain: str, hashed: str) -> bool:
            return False

    token = create_access_token({"sub": "ghost_user_not_in_store"})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token, _NeverFindsUser())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_active_user_raises_400_for_disabled_user() -> None:
    """get_current_active_user raises HTTP 400 when the user is disabled."""
    from fastapi import HTTPException

    from app.auth.models import User

    disabled_user = User(username="bob", disabled=True)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_active_user(disabled_user)
    assert exc_info.value.status_code == 400
