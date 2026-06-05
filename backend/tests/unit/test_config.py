"""Unit tests for ``app.config.Settings``.

Each test passes ``_env_file=None`` so the host environment / `.env` cannot
bleed into the assertion (otherwise an exported ``AMADEUS_*`` would silently
override the construction kwargs and mask regressions).
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_amadeus_env_default_is_test() -> None:
    assert Settings(_env_file=None).amadeus_env == "test"


def test_amadeus_env_rejects_invalid_value() -> None:
    # T-07-01 mitigation: Literal narrowing rejects anything outside the
    # known base-URL set, so no user-controlled URL can ever reach the
    # lifespan branch in Plan 03/04.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, amadeus_env="invalid")


@pytest.mark.parametrize("env", ["test", "prod", "mock"])
def test_amadeus_env_accepts_test_prod_mock(env: str) -> None:
    assert Settings(_env_file=None, amadeus_env=env).amadeus_env == env


def test_amadeus_credentials_default_is_none() -> None:
    s = Settings(_env_file=None)
    assert s.amadeus_api_key is None
    assert s.amadeus_api_secret is None


def test_amadeus_api_key_secretstr_scrubs_str() -> None:
    # T-07-02 mitigation: stringifying / repr'ing the SecretStr renders
    # '**********' so accidental log lines or f-strings cannot leak the
    # credential. ``.get_secret_value()`` is the only legitimate read path.
    s = Settings(
        _env_file=None,
        amadeus_api_key="real_secret_value",
        amadeus_api_secret="real_secret_value",
    )
    assert s.amadeus_api_key is not None
    assert s.amadeus_api_secret is not None
    assert "real_secret_value" not in str(s.amadeus_api_key)
    assert "real_secret_value" not in repr(s.amadeus_api_key)
    assert s.amadeus_api_key.get_secret_value() == "real_secret_value"
    assert "real_secret_value" not in str(s.amadeus_api_secret)
    assert s.amadeus_api_secret.get_secret_value() == "real_secret_value"
