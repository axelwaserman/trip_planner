"""Unit tests for POST /api/providers/refresh (D-06).

The route is exercised against a TestClient with the lifespan-constructed
``LLMProviderFactory`` monkeypatched so we can assert unconditional refresh
behaviour + the unreachable marker without spawning a real Ollama / LM Studio
daemon.

Note: TTL gating was removed from this endpoint (Phase 4.9 plan 04). The
explicit POST /api/providers/refresh always calls factory.refresh_local_models()
regardless of cache age — the user explicitly requested fresh data. TTL gating
is only applied by the GET /api/providers lazy-load path.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


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


def test_refresh_bypasses_cache_ttl(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — pre-populate cache with fresh-looking data (TTL not yet expired)
    import time as time_module

    now = time_module.time()
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()
    client.app.state.provider_models_cache["ollama"] = ["cached-model"]
    client.app.state.provider_models_cache_timestamps["ollama"] = now
    client.app.state.provider_models_cache["lmstudio"] = ["cached-lm"]
    client.app.state.provider_models_cache_timestamps["lmstudio"] = now

    # Even though the cache appears fresh, the explicit refresh endpoint
    # must ALWAYS call factory.refresh_local_models().
    called = {"count": 0}

    async def fake_refresh() -> dict[str, list[str] | None]:
        called["count"] += 1
        return {"ollama": ["fresh-model"], "lmstudio": []}

    monkeypatch.setattr(
        client.app.state.llm_factory,
        "refresh_local_models",
        fake_refresh,
    )

    # Act
    response = client.post("/api/providers/refresh", headers=auth_headers)

    # Assert — refresh_local_models was called unconditionally; response
    # reflects the newly-discovered models, not the stale cache.
    assert response.status_code == 200
    body = response.json()
    ollama_entry = next(p for p in body["providers"] if p["name"] == "ollama")
    assert ollama_entry["models"] == ["fresh-model"]
    assert called["count"] == 1
