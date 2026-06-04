"""Integration tests for GET /api/providers (D-25).

Verifies the dynamic-discovery wiring:

- Local providers (ollama, lmstudio) read their model list from
  ``app.state.provider_models_cache`` populated by
  :meth:`LLMProviderFactory.refresh_local_models`.
- Cloud providers (openai, anthropic) keep the curated static list.
- Every entry now exposes ``base_url``: populated for local, ``None`` for cloud.
- First-load lazy refresh: an empty cache triggers a one-shot
  ``refresh_local_models`` call before responding.
- Unreachable daemon: cached as ``[]`` with ``available=False``.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


def test_get_providers_serves_from_populated_cache(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-populate the cache; assert the response reflects it without re-probing."""
    # Arrange — seed cache + timestamps so the route does NOT trigger a lazy refresh.
    import time as time_module

    now = time_module.time()
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()
    client.app.state.provider_models_cache["ollama"] = ["qwen3:4b", "mistral:7b"]
    client.app.state.provider_models_cache_timestamps["ollama"] = now
    client.app.state.provider_models_cache["lmstudio"] = []
    client.app.state.provider_models_cache_timestamps["lmstudio"] = now

    # Make the factory's refresh method blow up if called — proves we served from cache.
    async def fail_refresh() -> dict[str, list[str] | None]:
        raise AssertionError("refresh_local_models should NOT be called when cache is populated")

    monkeypatch.setattr(client.app.state.llm_factory, "refresh_local_models", fail_refresh)

    # Act
    response = client.get("/api/providers", headers=auth_headers)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["ollama"]["models"] == ["qwen3:4b", "mistral:7b"]
    assert body["ollama"]["available"] is True
    assert body["lmstudio"]["models"] == []
    assert body["lmstudio"]["available"] is False


def test_get_providers_lazy_loads_on_first_call(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty cache → first GET triggers a single refresh_local_models call."""
    # Arrange — cache empty so lazy load fires
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()

    call_count = {"count": 0}

    async def fake_refresh() -> dict[str, list[str] | None]:
        call_count["count"] += 1
        return {"ollama": ["qwen3:4b"], "lmstudio": []}

    monkeypatch.setattr(client.app.state.llm_factory, "refresh_local_models", fake_refresh)

    # Act 1 — first call triggers lazy refresh
    r1 = client.get("/api/providers", headers=auth_headers)
    assert r1.status_code == 200
    assert call_count["count"] == 1
    assert r1.json()["ollama"]["models"] == ["qwen3:4b"]

    # Act 2 — second call serves from cache, no extra refresh
    r2 = client.get("/api/providers", headers=auth_headers)
    assert r2.status_code == 200
    assert call_count["count"] == 1, "second GET must NOT re-trigger refresh"
    assert r2.json()["ollama"]["models"] == ["qwen3:4b"]


def test_get_providers_marks_unreachable_daemon(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """factory.refresh_local_models returns None for ollama → models=[], available=False."""
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()

    async def fake_refresh() -> dict[str, list[str] | None]:
        return {"ollama": None, "lmstudio": None}

    monkeypatch.setattr(client.app.state.llm_factory, "refresh_local_models", fake_refresh)

    response = client.get("/api/providers", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ollama"]["models"] == []
    assert body["ollama"]["available"] is False
    assert body["lmstudio"]["models"] == []
    assert body["lmstudio"]["available"] is False


def test_get_providers_includes_base_url(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local providers carry base_url from Settings; cloud providers carry api_key_configured.

    Phase 6 / Plan 06-05a (REQ-p5-provider-info-split): the legacy
    ``ProviderInfo`` shape (every entry exposing ``base_url`` even for cloud)
    is replaced by a discriminated union — local providers expose ``base_url``
    only; cloud providers expose ``api_key_configured`` only and never the
    ``api_key`` itself (D-09 lock).
    """
    # Arrange — populate cache so we don't depend on a live daemon
    import time as time_module

    now = time_module.time()
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()
    client.app.state.provider_models_cache["ollama"] = ["qwen3:4b"]
    client.app.state.provider_models_cache_timestamps["ollama"] = now
    client.app.state.provider_models_cache["lmstudio"] = []
    client.app.state.provider_models_cache_timestamps["lmstudio"] = now

    response = client.get("/api/providers", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    # Local providers — type=local, base_url from Settings.
    assert body["ollama"]["type"] == "local"
    assert body["ollama"]["base_url"] == settings.ollama_base_url
    assert body["lmstudio"]["type"] == "local"
    assert body["lmstudio"]["base_url"] == settings.lmstudio_base_url
    # Cloud providers — type=cloud, api_key_configured boolean only.
    assert body["openai"]["type"] == "cloud"
    assert "api_key_configured" in body["openai"]
    assert "base_url" not in body["openai"]
    assert "api_key" not in body["openai"]
    assert body["anthropic"]["type"] == "cloud"
    assert "api_key_configured" in body["anthropic"]
    assert "base_url" not in body["anthropic"]
    assert "api_key" not in body["anthropic"]


def test_get_providers_keeps_curated_cloud_models(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud entries (openai, anthropic) carry the curated static list — no live probe."""
    # Pre-populate cache so local entries don't trigger a refresh.
    import time as time_module

    now = time_module.time()
    client.app.state.provider_models_cache.clear()
    client.app.state.provider_models_cache_timestamps.clear()
    client.app.state.provider_models_cache["ollama"] = ["qwen3:4b"]
    client.app.state.provider_models_cache_timestamps["ollama"] = now
    client.app.state.provider_models_cache["lmstudio"] = []
    client.app.state.provider_models_cache_timestamps["lmstudio"] = now

    response = client.get("/api/providers", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    # Curated lists are non-empty and include the canonical defaults.
    assert "gpt-4o-mini" in body["openai"]["models"]
    assert "claude-3-5-sonnet-20241022" in body["anthropic"]["models"]


def test_get_providers_requires_auth(client: TestClient) -> None:
    """GET /api/providers without a Bearer token returns 401."""
    response = client.get("/api/providers")
    assert response.status_code == 401
