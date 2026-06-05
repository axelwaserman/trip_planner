"""Lifespan flight-provider branch tests (Phase 7 / Plan 07-05, D-04 + D-05).

The Plan-07-05 lifespan branches on ``Settings.amadeus_env`` AND credential
presence:

* ``amadeus_env == "mock"`` OR either credential ``None`` -> ``MockFlightAPIClient``
  + ``flight_provider == "mock"``. The missing-creds branch additionally logs
  WARN ``"AMADEUS_* creds missing — falling back to MockFlightAPIClient"``.
* Otherwise -> ``AmadeusFlightClient`` against
  ``"https://test.api.amadeus.com"`` (test env) or ``"https://api.amadeus.com"``
  (prod env), with credentials unpacked via ``SecretStr.get_secret_value``.

These tests drive the lifespan via ``with TestClient(app) as client:`` so the
real startup path runs. Settings overrides go through ``monkeypatch.setattr``
on the module-level ``app.config.settings`` singleton — Settings is not frozen,
so attribute mutation is safe inside a single test (``monkeypatch`` rolls back
between tests).

No real HTTP traffic occurs: the lifespan only constructs the client; the
OAuth token is fetched lazily on first ``_get_token()`` await, which never
happens in these tests.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import app
from app.flights.amadeus_client import AmadeusFlightClient
from app.tools.flight_client import MockFlightAPIClient


def test_lifespan_uses_mock_when_amadeus_env_is_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """``amadeus_env == "mock"`` short-circuits to MockFlightAPIClient.

    No WARN log is emitted on this branch — the user explicitly opted into
    mock mode.
    """
    monkeypatch.setattr("app.config.settings.amadeus_env", "mock")
    monkeypatch.setattr("app.config.settings.amadeus_api_key", None)
    monkeypatch.setattr("app.config.settings.amadeus_api_secret", None)

    with TestClient(app) as client:
        # Touch the app so lifespan-stashed state is observable.
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "mock"
        assert isinstance(app.state.flight_client, MockFlightAPIClient)


def test_lifespan_falls_back_to_mock_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Real env + missing creds -> mock fallback with a WARN log.

    Plan 06's CI inspection may parse the log line for the literal substring
    ``"AMADEUS_* creds missing"``; this test locks the wording.
    """
    monkeypatch.setattr("app.config.settings.amadeus_env", "test")
    monkeypatch.setattr("app.config.settings.amadeus_api_key", None)
    monkeypatch.setattr("app.config.settings.amadeus_api_secret", None)

    with (
        caplog.at_level(logging.WARNING, logger="app.api.main"),
        TestClient(app) as client,
    ):
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "mock"
        assert isinstance(app.state.flight_client, MockFlightAPIClient)

    assert any(
        "AMADEUS_* creds missing" in record.message for record in caplog.records
    ), f"expected WARN line not found; saw {[r.message for r in caplog.records]}"


def test_lifespan_constructs_amadeus_client_with_real_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real env + present creds -> AmadeusFlightClient against the test base URL.

    No real HTTP traffic occurs — the lifespan only constructs the client.
    """
    monkeypatch.setattr("app.config.settings.amadeus_env", "test")
    monkeypatch.setattr(
        "app.config.settings.amadeus_api_key", SecretStr("fake_key_value")
    )
    monkeypatch.setattr(
        "app.config.settings.amadeus_api_secret", SecretStr("fake_secret_value")
    )

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "real"
        assert isinstance(app.state.flight_client, AmadeusFlightClient)
        # T-07-01 mitigation: lock the constructed base URL for the test env.
        assert (
            app.state.flight_client._base_url == "https://test.api.amadeus.com"
        )
