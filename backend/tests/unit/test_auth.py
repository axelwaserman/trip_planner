"""Unit tests for auth module — JWT + password helpers + repository contract.

Phase 6 / Plan 06-04 (D-07): the ``EnvUserRepository`` user-loading tests
retired with the class itself. Repository-shape coverage in this file is
limited to the ABC contract and the pwdlib verify_password path against a
hand-rolled :class:`UserRepository` test double — the live PostgresUserRepository
gets its end-to-end coverage from ``tests/integration/db/test_auth_postgres_login.py``.
"""

from datetime import timedelta

import pytest

from app.auth.routes import (
    create_access_token,
    get_current_active_user,
    get_current_user,
)

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
        async def get_user(self, username: str) -> UserInDB:
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
        async def get_user(self, username: str) -> UserInDB:
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


# ---------------------------------------------------------------------------
# Timing equalisation mechanism — _DUMMY_HASH
# ---------------------------------------------------------------------------


def test_login_unknown_user_dummy_hash_is_precomputed_argon2() -> None:
    """_DUMMY_HASH must be a non-empty pre-computed Argon2 hash.

    Login must call verify_password even for unknown users to equalise timing
    and prevent username enumeration. This test guards that the mechanism exists:
    _DUMMY_HASH is exported from app.auth.repository as a non-empty Argon2 hash
    string that can be passed to verify_password in the unknown-user branch.
    """
    from app.auth.repository import _DUMMY_HASH

    assert _DUMMY_HASH, "_DUMMY_HASH must be a non-empty pre-computed Argon2 hash"
    assert _DUMMY_HASH.startswith("$argon2"), "_DUMMY_HASH must be an Argon2 hash"


# ---------------------------------------------------------------------------
# verify_password — Argon2 round-trip via the canonical _password_hasher singleton
# ---------------------------------------------------------------------------


def test_verify_password_returns_true_for_correct_password() -> None:
    """The shared _password_hasher singleton verifies a freshly-hashed password."""
    from app.auth.repository import _password_hasher

    hashed = _password_hasher.hash("mypassword")
    assert _password_hasher.verify("mypassword", hashed) is True


def test_verify_password_returns_false_for_wrong_password() -> None:
    """The shared _password_hasher singleton rejects a non-matching plain text."""
    from app.auth.repository import _password_hasher

    hashed = _password_hasher.hash("correct")
    assert _password_hasher.verify("wrong", hashed) is False
