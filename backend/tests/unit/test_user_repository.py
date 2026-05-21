"""Unit tests for EnvUserRepository — tests user loading and password verification.

TDD RED phase: These tests import from app.auth.repository which does not exist yet.
They are expected to fail with ImportError until Task 2 creates the module.
"""

import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.auth.models import UserNotFoundError
from app.auth.repository import EnvUserRepository

# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


def test_get_user_returns_correct_userinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    """EnvUserRepository.get_user returns UserInDB for a known username.

    Arrange: AUTH_USERS env var contains a single user "alice:secret".
    Act: Call get_user("alice").
    Assert: Returns UserInDB with username="alice" and a non-empty hashed_password.
    """
    monkeypatch.setenv("AUTH_USERS", "alice:secret")
    repo = EnvUserRepository()
    user = repo.get_user("alice")
    assert user is not None
    assert user.username == "alice"
    assert user.hashed_password != "secret"
    assert len(user.hashed_password) > 0


def test_get_user_raises_for_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """EnvUserRepository.get_user raises UserNotFoundError for an unknown username.

    Arrange: AUTH_USERS env var contains only "alice:secret".
    Act: Call get_user("unknown").
    Assert: Raises UserNotFoundError.
    """
    monkeypatch.setenv("AUTH_USERS", "alice:secret")
    repo = EnvUserRepository()
    with pytest.raises(UserNotFoundError, match="unknown"):
        repo.get_user("unknown")


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------


def test_verify_password_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    """EnvUserRepository.verify_password returns True for correct password.

    Arrange: Hash "secret" with the same hasher used by EnvUserRepository.
    Act: Call verify_password("secret", hashed).
    Assert: Returns True.
    """
    monkeypatch.setenv("AUTH_USERS", "alice:secret")
    repo = EnvUserRepository()
    ph = PasswordHash([Argon2Hasher()])
    hashed = ph.hash("secret")
    assert repo.verify_password("secret", hashed) is True


def test_verify_password_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    """EnvUserRepository.verify_password returns False for wrong password.

    Arrange: Hash "secret" with the same hasher.
    Act: Call verify_password("wrong", hashed).
    Assert: Returns False.
    """
    monkeypatch.setenv("AUTH_USERS", "alice:secret")
    repo = EnvUserRepository()
    ph = PasswordHash([Argon2Hasher()])
    hashed = ph.hash("secret")
    assert repo.verify_password("wrong", hashed) is False
