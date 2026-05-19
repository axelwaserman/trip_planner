"""Integration-test fixtures.

The Phase 4.5 ``OllamaProvider.validate_config`` probe hits
``GET {base_url}/api/tags`` whenever a session is created with the default
provider. Locally that succeeds against a running Ollama daemon; in CI no
daemon is reachable and every ``POST /api/chat/session`` returns 502.

The autouse fixture below patches ``httpx.AsyncClient.get`` for every
integration test by default to return a happy-path tags response containing
the default model. Tests that need to exercise specific probe outcomes
(see :mod:`tests.integration.test_session_probe`) re-monkeypatch
``httpx.AsyncClient.get`` themselves and the more-specific patch wins.

The mocked endpoint matches Ollama's ``/api/tags`` shape AND LM Studio's
``/v1/models`` shape so the same fixture covers both local providers.
Cloud providers (OpenAI / Anthropic) don't go through this path — their
probe is request-driven on the ``/test`` endpoint.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


def _default_tags_response() -> MagicMock:
    """Mimic httpx.Response for both Ollama /api/tags and LM Studio /v1/models.

    The default Ollama probe asks for ``qwen3:4b`` per ``Settings.default_model``;
    we list it (and a small set of common models) so the probe passes.
    """
    response = MagicMock()
    response.raise_for_status = MagicMock(return_value=None)
    response.json = MagicMock(
        return_value={
            # Ollama /api/tags shape
            "models": [
                {"name": "qwen3:4b", "model": "qwen3:4b"},
                {"name": "mistral:7b", "model": "mistral:7b"},
            ],
            # LM Studio /v1/models shape (parallel keys; clients pick whichever
            # they understand). The OpenAI-compatible shape uses `data`.
            "object": "list",
            "data": [
                {"id": "qwen3:4b", "object": "model"},
                {"id": "mistral:7b", "object": "model"},
            ],
        }
    )
    return response


@pytest.fixture(autouse=True)
def _stub_local_provider_probes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Auto-stub httpx.AsyncClient.get for every integration test.

    Tests that opt out by re-monkeypatching ``httpx.AsyncClient.get`` will see
    their patch override this one (the closer-scoped patch wins). Tests that
    need the real probe (none in CI) can request the ``unmocked_httpx``
    fixture to skip this stub.
    """
    if "unmocked_httpx" in request.fixturenames:
        yield
        return
    monkeypatch.setattr(
        httpx.AsyncClient,
        "get",
        AsyncMock(return_value=_default_tags_response()),
    )
    yield


@pytest.fixture
def unmocked_httpx() -> None:
    """Marker fixture — request to skip the autouse probe stub."""
    return None
