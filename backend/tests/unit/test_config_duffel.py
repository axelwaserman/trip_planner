"""Unit tests locking the Phase 7 D-01 Duffel credential surface on ``Settings``.

Covers five behaviours:

* Test 1 — Pitfall 6: ``Settings(duffel_api_token=None)`` succeeds (no
  ``ValidationError``). A fresh checkout with no Duffel account must boot.
* Test 2 — T-07-02-class: ``DUFFEL_API_TOKEN=duffel_test_...`` env yields a
  ``SecretStr`` whose ``repr()`` does NOT contain the raw token. SecretStr
  opacity is the first-line defence against debug dumps.
* Test 3 — D-01: default ``duffel_env == "test"`` (sandbox by default).
* Test 4 — D-01 / Literal narrowing: ``DUFFEL_ENV=staging`` raises
  ``ValidationError``. Only ``"test" | "live" | "mock"`` accepted.
* Test 5 — D-01 / D-02: ``DUFFEL_ENV=mock`` is the third allowed literal
  (forces mock client even when a token is present, used by Plan 07-03 lifespan).

Tests use ``monkeypatch.setenv`` for env-var-driven cases; the no-env-var
default test instantiates ``Settings(duffel_api_token=None)`` directly so a
developer-local ``DUFFEL_API_TOKEN`` does not leak into the assertion.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings


def test_settings_accepts_none_duffel_token_without_validation_error() -> None:
    # Arrange / Act — Pitfall 6: missing token must not crash boot.
    s = Settings(duffel_api_token=None)

    # Assert
    assert s.duffel_api_token is None


def test_settings_wraps_env_duffel_token_in_secretstr_with_opaque_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — T-07-02-class: SecretStr opacity in repr.
    raw_token = "duffel_test_xxxxxxxxxxxxxxxxxxxx"
    monkeypatch.setenv("DUFFEL_API_TOKEN", raw_token)

    # Act
    s = Settings()

    # Assert
    assert isinstance(s.duffel_api_token, SecretStr)
    assert s.duffel_api_token.get_secret_value() == raw_token
    assert "duffel_test_xxxx" not in repr(s.duffel_api_token)


def test_settings_default_duffel_env_is_test(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — guard against a developer's local DUFFEL_ENV leaking in.
    monkeypatch.delenv("DUFFEL_ENV", raising=False)

    # Act
    s = Settings(duffel_api_token=None)

    # Assert — D-01: default literal is "test".
    assert s.duffel_env == "test"


def test_settings_rejects_invalid_duffel_env_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — D-01: Literal narrowing rejects unknown values.
    monkeypatch.setenv("DUFFEL_ENV", "staging")

    # Act / Assert
    with pytest.raises(ValidationError):
        Settings(duffel_api_token=None)


def test_settings_accepts_mock_duffel_env_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — D-01 / D-02: "mock" is the third allowed literal.
    monkeypatch.setenv("DUFFEL_ENV", "mock")

    # Act
    s = Settings(duffel_api_token=None)

    # Assert
    assert s.duffel_env == "mock"
