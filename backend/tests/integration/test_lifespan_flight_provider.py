"""Lifespan flight-provider branch tests (Phase 7 / Plan 07-03, D-01 + D-02).

The lifespan branches on ``Settings.duffel_env`` AND token presence:

* ``duffel_env == "mock"`` OR ``duffel_api_token`` falsy -> MockFlightAPIClient
  + flight_provider == "mock". The missing-token branch additionally logs
  WARN ``"DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient"``;
  the explicit-mock branch is silent (the operator opted in).
* Otherwise -> DuffelFlightClient against ``"https://api.duffel.com"``,
  with token unpacked via SecretStr.get_secret_value().
"""

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import app
from app.flights.duffel_client import DuffelFlightClient
from app.tools.flight_client import MockFlightAPIClient


def test_lifespan_uses_mock_when_duffel_env_is_mock(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """duffel_env == 'mock' short-circuits to MockFlightAPIClient. No WARN log."""
    monkeypatch.setattr("app.config.settings.duffel_env", "mock")
    monkeypatch.setattr("app.config.settings.duffel_api_token", None)
    with (
        caplog.at_level(logging.WARNING, logger="app.api.main"),
        TestClient(app) as client,
    ):
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "mock"
        assert isinstance(app.state.flight_client, MockFlightAPIClient)
    # Explicit mock is silent: no DUFFEL_API_TOKEN missing WARN should fire.
    assert not any("DUFFEL_API_TOKEN missing" in record.message for record in caplog.records)


def test_lifespan_falls_back_to_mock_when_token_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Real env + missing token -> mock fallback with WARN log (D-02 + Pitfall 6)."""
    monkeypatch.setattr("app.config.settings.duffel_env", "test")
    monkeypatch.setattr("app.config.settings.duffel_api_token", None)
    with (
        caplog.at_level(logging.WARNING, logger="app.api.main"),
        TestClient(app) as client,
    ):
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "mock"
        assert isinstance(app.state.flight_client, MockFlightAPIClient)
    assert any("DUFFEL_API_TOKEN missing" in record.message for record in caplog.records)


def test_lifespan_constructs_duffel_client_with_real_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real env + present token -> DuffelFlightClient against api.duffel.com."""
    monkeypatch.setattr("app.config.settings.duffel_env", "test")
    monkeypatch.setattr(
        "app.config.settings.duffel_api_token",
        SecretStr("duffel_test_fake_xxxxxxxxxxxxxxxx"),
    )
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "real"
        assert isinstance(app.state.flight_client, DuffelFlightClient)
        # Threat-model T-07-03-01: the test never inspects the stored token —
        # only the public-shape _base_url attribute is asserted.
        assert app.state.flight_client._base_url == "https://api.duffel.com"
