"""Unit tests for POST /api/providers/refresh (D-06).

The route is exercised against a TestClient with the lifespan-constructed
``LLMProviderFactory`` monkeypatched so we can assert TTL-gating + the
unreachable marker without spawning a real Ollama / LM Studio daemon.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def test_refresh_returns_401_without_auth(client: TestClient) -> None:
    # Arrange / Act
    response = client.post("/api/providers/refresh")

    # Assert
    assert response.status_code == 401


def test_refresh_returns_200_with_discovered_models(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — mock factory.refresh_local_models
    async def fake_refresh() -> dict[str, list[str] | None]:
        return {"ollama": ["qwen3:4b", "mistral:7b"], "lmstudio": []}

    # Patch on the factory instance held in app.state
    monkeypatch.setattr(
        client.app.state.llm_factory,
        "refresh_local_models",
        fake_refresh,
    )
    # Reset cache + timestamps to force a fresh refresh
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()

    # Act
    response = client.post("/api/providers/refresh", headers=auth_headers)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    ollama_entry = next(p for p in body["providers"] if p["name"] == "ollama")
    assert ollama_entry["models"] == ["qwen3:4b", "mistral:7b"]
    assert ollama_entry["available"] is True
    assert ollama_entry["error"] is None


def test_refresh_marks_unreachable_provider(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — refresh returns None for a daemon (the "unreachable" sentinel)
    async def fake_refresh() -> dict[str, list[str] | None]:
        return {"ollama": None, "lmstudio": None}

    monkeypatch.setattr(
        client.app.state.llm_factory,
        "refresh_local_models",
        fake_refresh,
    )
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()

    # Act
    response = client.post("/api/providers/refresh", headers=auth_headers)

    # Assert — partial success returns 200 with the provider marked unavailable
    assert response.status_code == 200
    body = response.json()
    ollama_entry = next(p for p in body["providers"] if p["name"] == "ollama")
    assert ollama_entry["available"] is False
    assert ollama_entry["error"] == "provider_unreachable"
    assert ollama_entry["models"] == []


def test_refresh_respects_cache_ttl(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — pre-populate cache + timestamps so the call is a cache hit
    import time as time_module

    now = time_module.time()
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()
    client.app.state.provider_models_cache["ollama"] = ["cached-model"]
    client.app.state.provider_models_cache_timestamps["ollama"] = now
    client.app.state.provider_models_cache["lmstudio"] = ["cached-lm"]
    client.app.state.provider_models_cache_timestamps["lmstudio"] = now

    # If refresh is called, the test fails — make sure it's NOT called.
    called = {"count": 0}

    async def fake_refresh() -> dict[str, list[str] | None]:
        called["count"] += 1
        return {"ollama": ["this-should-not-appear"], "lmstudio": []}

    monkeypatch.setattr(
        client.app.state.llm_factory,
        "refresh_local_models",
        fake_refresh,
    )

    # Act
    response = client.post("/api/providers/refresh", headers=auth_headers)

    # Assert — cache hit; refresh_local_models was NOT called
    assert response.status_code == 200
    body = response.json()
    ollama_entry = next(p for p in body["providers"] if p["name"] == "ollama")
    assert ollama_entry["models"] == ["cached-model"]
    assert called["count"] == 0
