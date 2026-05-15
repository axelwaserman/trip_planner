"""Integration tests for the provider probe wired into POST /api/chat/session.

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

    The probe is the authority for the missing-key signal — the route no longer
    short-circuits on ``available=False``.
    """
    from app.services import provider_probe as probe_module

    monkeypatch.setattr(probe_module.settings, "openai_api_key", None, raising=False)

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
