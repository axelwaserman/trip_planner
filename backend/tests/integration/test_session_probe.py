"""Integration tests for the provider probe wired into POST /api/chat/conversation.

Plan 4.2-04 inserts ``await probe_provider(provider, model)`` between the existing
provider validation and ``chat_service.create_session()``. These tests monkeypatch
``httpx.AsyncClient.get`` so we exercise the four probe outcomes without needing
a live Ollama daemon.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def _make_tags_response(models: list[dict[str, str]]) -> MagicMock:
    """Return a MagicMock that mimics httpx.Response for /api/tags."""
    response = MagicMock()
    response.raise_for_status = MagicMock(return_value=None)
    response.json = MagicMock(return_value={"models": models})
    return response


def test_session_create_returns_502_when_provider_unreachable(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectError from httpx.AsyncClient.get → 502 with structured provider_unreachable."""
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(side_effect=httpx.ConnectError("connection refused")),
    )

    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3:4b"}},
    )

    assert response.status_code == 502
    body = response.json()
    detail = body["detail"]
    assert detail["error"] == "provider_unreachable"
    assert "Ollama" in detail["message"]
    assert "ollama serve" in detail["hint"]


def test_session_create_returns_400_when_model_not_installed(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """/api/tags responds but does not list the requested model → 400 model_not_installed."""
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(
            return_value=_make_tags_response(
                [{"name": "other:7b", "model": "other:7b"}],
            ),
        ),
    )

    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3:4b"}},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "model_not_installed"
    assert "qwen3:4b" in body["detail"]["hint"]


def test_session_create_returns_400_when_cloud_key_missing(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENAI_API_KEY absent → probe returns 400 missing_api_key.

    The factory reads from ``Settings.openai_api_key`` at build time and
    constructs an OpenAIProvider with ``api_key=None``; the provider's
    :meth:`OpenAIProvider.validate_config` returns the structured
    ``MISSING_API_KEY`` error inside :meth:`ChatService.create_session`.
    """
    # Patch the module-level settings instance the route layer reads from.
    monkeypatch.setattr("app.config.settings.openai_api_key", None, raising=False)
    # Also clear it on the ChatService's factory's settings instance — the
    # lifespan-scoped factory captured a Settings() object at app construction.
    factory = client.app.state.llm_factory
    monkeypatch.setattr(factory._settings, "openai_api_key", None, raising=False)

    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "openai", "model": "gpt-4o-mini"}},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "missing_api_key"
    assert "OPENAI_API_KEY" in body["detail"]["hint"]


def test_session_create_succeeds_when_ollama_probe_passes(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """/api/tags lists the requested model → 201 with conversation_id."""
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(
            return_value=_make_tags_response(
                [{"name": "qwen3:4b", "model": "qwen3:4b"}],
            ),
        ),
    )

    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3:4b"}},
    )

    assert response.status_code == 201
    body = response.json()
    assert "conversation_id" in body
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:4b"


def test_session_create_accepts_model_outside_curated_list_when_daemon_has_it(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
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
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(
            return_value=_make_tags_response(
                [{"name": "qwen3.5:9b", "model": "qwen3.5:9b"}],
            ),
        ),
    )

    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "ollama", "model": "qwen3.5:9b"}},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["model"] == "qwen3.5:9b"


def test_session_create_rejects_unknown_provider_at_route_layer(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Unknown provider name still rejected at the route boundary (defense-in-depth).

    UAT round-3 only relaxed the model whitelist; the provider whitelist stays
    enforced because a typo there would otherwise reach the factory's
    match-default branch.
    """
    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "made-up-provider", "model": "anything"}},
    )
    assert response.status_code == 400
    body = response.json()
    assert "Invalid provider" in body["detail"]


def _make_lmstudio_models_response(model_ids: list[str]) -> MagicMock:
    """Return a MagicMock that mimics httpx.Response for LM Studio's /models."""
    response = MagicMock()
    response.raise_for_status = MagicMock(return_value=None)
    response.json = MagicMock(
        return_value={
            "object": "list",
            "data": [{"id": mid, "object": "model"} for mid in model_ids],
        }
    )
    return response


def test_session_create_accepts_lmstudio_provider_at_route_layer(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for AR-01: ``provider="lmstudio"`` must pass the route validator.

    Before AR-01's fix, ``Settings.get_available_providers()`` only listed
    ``ollama``/``openai``/``anthropic`` — every ``POST /api/chat/conversation`` with
    ``provider="lmstudio"`` returned HTTP 400 ``"Invalid provider: lmstudio"``
    before the factory was ever reached, making the entire LM Studio
    implementation unreachable from the frontend. This test asserts the
    provider name is now accepted: with a mocked LM Studio daemon the call
    proceeds to the probe and returns 201.
    """
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(
            return_value=_make_lmstudio_models_response(["qwen2.5-coder-7b"]),
        ),
    )

    response = client.post(
        "/api/chat/conversation",
        headers=auth_headers,
        json={"target": {"provider": "lmstudio", "model": "qwen2.5-coder-7b"}, "credentials": {"base_url": "http://localhost:1234/v1"}},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "lmstudio"
    assert body["model"] == "qwen2.5-coder-7b"
    assert "conversation_id" in body


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
