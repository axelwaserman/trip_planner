"""Integration tests for the provider probe wired into POST /api/chat/session.

Phase 5 (plan 05-07) migrated OllamaProvider and LMStudioProvider from httpx
to pyreqwest (ADR-008). These tests patch the pyreqwest ``ClientBuilder`` call
chain so we exercise the four probe outcomes without needing a live daemon.

Call chain under test:
    async with ClientBuilder().timeout(...).error_for_status(True).build() as client:
        resp = await client.get(url).build().send()
        payload = await resp.json()
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pyreqwest.exceptions import CauseErrorDetails, ConnectError

from app.api.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def _make_pyreqwest_builder(payload: dict[str, Any]) -> MagicMock:
    """Return a MagicMock ClientBuilder whose call chain yields ``payload``."""
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)

    request_mock = MagicMock()
    request_mock.send = AsyncMock(return_value=response)

    request_builder = MagicMock()
    request_builder.build = MagicMock(return_value=request_mock)

    client = AsyncMock()
    client.get = MagicMock(return_value=request_builder)

    @asynccontextmanager
    async def _cm(*_: Any, **__: Any) -> AsyncGenerator[AsyncMock]:
        yield client

    builder_instance = MagicMock()
    builder_instance.timeout = MagicMock(return_value=builder_instance)
    builder_instance.error_for_status = MagicMock(return_value=builder_instance)
    builder_instance.build = MagicMock(return_value=_cm())

    return MagicMock(return_value=builder_instance)


def _make_pyreqwest_builder_raising(exc: Exception) -> MagicMock:
    """Return a MagicMock ClientBuilder whose ``.send()`` raises ``exc``."""
    request_mock = MagicMock()
    request_mock.send = AsyncMock(side_effect=exc)

    request_builder = MagicMock()
    request_builder.build = MagicMock(return_value=request_mock)

    client = AsyncMock()
    client.get = MagicMock(return_value=request_builder)

    @asynccontextmanager
    async def _cm(*_: Any, **__: Any) -> AsyncGenerator[AsyncMock]:
        yield client

    builder_instance = MagicMock()
    builder_instance.timeout = MagicMock(return_value=builder_instance)
    builder_instance.error_for_status = MagicMock(return_value=builder_instance)
    builder_instance.build = MagicMock(return_value=_cm())

    return MagicMock(return_value=builder_instance)


def _ollama_tags_payload(models: list[str]) -> dict[str, Any]:
    return {"models": [{"name": m, "model": m} for m in models]}


def _lmstudio_models_payload(model_ids: list[str]) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [{"id": mid, "object": "model"} for mid in model_ids],
    }


def test_session_create_returns_502_when_provider_unreachable(client: TestClient, auth_headers: dict[str, str]) -> None:
    """ConnectError from pyreqwest → 502 with structured provider_unreachable."""
    builder = _make_pyreqwest_builder_raising(ConnectError("connection refused", CauseErrorDetails()))
    with patch("app.llm.providers.ollama.ClientBuilder", builder):
        response = client.post(
            "/api/chat/session",
            headers=auth_headers,
            json={"provider": "ollama", "model": "qwen3:4b"},
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error"] == "provider_unreachable"
    assert "Ollama" in detail["message"]
    assert "ollama serve" in detail["hint"]


def test_session_create_returns_400_when_model_not_installed(client: TestClient, auth_headers: dict[str, str]) -> None:
    """/api/tags responds but does not list the requested model → 400 model_not_installed."""
    builder = _make_pyreqwest_builder(_ollama_tags_payload(["other:7b"]))
    with patch("app.llm.providers.ollama.ClientBuilder", builder):
        response = client.post(
            "/api/chat/session",
            headers=auth_headers,
            json={"provider": "ollama", "model": "qwen3:4b"},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "model_not_installed"
    assert "qwen3:4b" in detail["hint"]


def test_session_create_returns_400_when_cloud_key_missing(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENAI_API_KEY absent → probe returns 400 missing_api_key.

    The factory reads from ``Settings.openai_api_key`` at build time and
    constructs an OpenAIProvider with ``api_key=None``; the provider's
    :meth:`OpenAIProvider.validate_config` returns the structured
    ``MISSING_API_KEY`` error inside :meth:`ChatService.create_session`.
    """
    monkeypatch.setattr("app.config.settings.openai_api_key", None, raising=False)
    factory = client.app.state.llm_factory
    monkeypatch.setattr(factory._settings, "openai_api_key", None, raising=False)

    response = client.post(
        "/api/chat/session",
        headers=auth_headers,
        json={"provider": "openai", "model": "gpt-4o-mini"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "missing_api_key"
    assert "OPENAI_API_KEY" in detail["hint"]


def test_session_create_succeeds_when_ollama_probe_passes(client: TestClient, auth_headers: dict[str, str]) -> None:
    """/api/tags lists the requested model → 201 with session_id."""
    builder = _make_pyreqwest_builder(_ollama_tags_payload(["qwen3:4b"]))
    with patch("app.llm.providers.ollama.ClientBuilder", builder):
        response = client.post(
            "/api/chat/session",
            headers=auth_headers,
            json={"provider": "ollama", "model": "qwen3:4b"},
        )

    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:4b"


def test_session_create_accepts_model_outside_curated_list_when_daemon_has_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """UAT round-3 regression guard: a daemon-installed model NOT in the curated
    frozen list (e.g. ``qwen3.5:9b`` after the user pulled it) must succeed.

    Previous behaviour: route-level whitelist rejected with 400 "Invalid model"
    before the probe could run, locking users out of any model not hand-listed
    in ``Settings.get_available_providers()``. New behaviour: the route does
    not enforce a model whitelist for local providers — the per-provider probe
    consults ``/api/tags`` and surfaces structured ``MODEL_NOT_INSTALLED`` only
    when the daemon actually doesn't have the model.
    """
    builder = _make_pyreqwest_builder(_ollama_tags_payload(["qwen3.5:9b"]))
    with patch("app.llm.providers.ollama.ClientBuilder", builder):
        response = client.post(
            "/api/chat/session",
            headers=auth_headers,
            json={"provider": "ollama", "model": "qwen3.5:9b"},
        )

    assert response.status_code == 201
    assert response.json()["model"] == "qwen3.5:9b"


def test_session_create_rejects_unknown_provider_at_route_layer(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Unknown provider name still rejected at the route boundary (defense-in-depth).

    UAT round-3 only relaxed the model whitelist; the provider whitelist stays
    enforced because a typo there would otherwise reach the factory's
    match-default branch.
    """
    response = client.post(
        "/api/chat/session",
        headers=auth_headers,
        json={"provider": "made-up-provider", "model": "anything"},
    )
    assert response.status_code == 400
    assert "Invalid provider" in response.json()["detail"]


def test_session_create_accepts_lmstudio_provider_at_route_layer(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Regression for AR-01: ``provider="lmstudio"`` must pass the route validator.

    Before AR-01's fix, ``Settings.get_available_providers()`` only listed
    ``ollama``/``openai``/``anthropic`` — every ``POST /api/chat/session`` with
    ``provider="lmstudio"`` returned HTTP 400 ``"Invalid provider: lmstudio"``
    before the factory was ever reached, making the entire LM Studio
    implementation unreachable from the frontend. This test asserts the
    provider name is now accepted: with a mocked LM Studio daemon the call
    proceeds to the probe and returns 201.
    """
    builder = _make_pyreqwest_builder(_lmstudio_models_payload(["qwen2.5-coder-7b"]))
    with patch("app.llm.providers.lmstudio.ClientBuilder", builder):
        response = client.post(
            "/api/chat/session",
            headers=auth_headers,
            json={
                "provider": "lmstudio",
                "model": "qwen2.5-coder-7b",
                "base_url": "http://localhost:1234/v1",
            },
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "lmstudio"
    assert body["model"] == "qwen2.5-coder-7b"
    assert "session_id" in body


def test_get_available_providers_lists_all_factory_dispatch_arms() -> None:
    """Regression for AR-01: every provider the factory builds must be listed.

    The factory has match arms for ``ollama``, ``lmstudio``, ``openai``, and
    ``anthropic``. ``Settings.get_available_providers()`` is the route-layer
    whitelist; if any factory arm is missing here the route returns 400
    before the factory is reached, silently making that provider unreachable.
    This test fails if a future contributor adds a factory arm without also
    registering it on ``Settings``.
    """
    from app.config import Settings

    expected_providers = {"ollama", "lmstudio", "openai", "anthropic"}
    actual_providers = set(Settings().get_available_providers().keys())
    assert actual_providers == expected_providers
