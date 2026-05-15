"""Integration tests for the provider probe wired into POST /api/chat/session.

Plan 4.2-04 inserts ``await probe_provider(provider, model)`` between the existing
provider validation and ``chat_service.create_session()``. These tests monkeypatch
``httpx.AsyncClient.get`` so we exercise the four probe outcomes without needing
a live Ollama daemon.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.main import app

pytestmark = pytest.mark.integration


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
        "/api/chat/session",
        headers=auth_headers,
        json={"provider": "ollama", "model": "qwen3:4b"},
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
        "/api/chat/session",
        headers=auth_headers,
        json={"provider": "ollama", "model": "qwen3:4b"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "model_not_installed"
    assert "qwen3:4b" in body["detail"]["hint"]


def test_session_create_returns_400_when_cloud_key_missing(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENAI_API_KEY absent → probe returns 400 missing_api_key.

    The existing ``available=False`` 400 path also fires when no key is set, so
    we override ``get_available_providers`` to report openai as available; that
    lets the probe become the authority for the missing-key signal.
    """
    from app.api.routes import routes as routes_module
    from app.services import provider_probe as probe_module

    available_override: dict[str, dict[str, Any]] = {
        "ollama": {"available": True, "models": ["qwen3:4b"]},
        "openai": {"available": True, "models": ["gpt-4o-mini"]},
    }

    class FakeSettings:
        openai_api_key: str | None = None
        anthropic_api_key: str | None = None
        ollama_base_url: str = "http://localhost:11434"

        def get_available_providers(self) -> dict[str, dict[str, Any]]:
            return available_override

    fake_settings = FakeSettings()
    monkeypatch.setattr(routes_module, "settings", fake_settings)
    monkeypatch.setattr(probe_module, "settings", fake_settings)

    response = client.post(
        "/api/chat/session",
        headers=auth_headers,
        json={"provider": "openai", "model": "gpt-4o-mini"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "missing_api_key"
    assert "OPENAI_API_KEY" in body["detail"]["hint"]


def test_session_create_succeeds_when_ollama_probe_passes(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """/api/tags lists the requested model → 201 with session_id."""
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
        "/api/chat/session",
        headers=auth_headers,
        json={"provider": "ollama", "model": "qwen3:4b"},
    )

    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:4b"
