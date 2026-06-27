"""Integration-test fixtures.

OllamaProvider and LMStudioProvider (Phase 5 / Plan 05-07) use pyreqwest for
``GET {base_url}/api/tags`` and ``GET {base_url}/models`` respectively.  In CI
there is no daemon, so every ``POST /api/chat/session`` 502s unless we stub
the network call.

The autouse fixture below patches ``pyreqwest.client.ClientBuilder`` for every
integration test by default.  Tests that need to exercise specific probe
outcomes (see :mod:`tests.integration.test_session_probe`) re-monkeypatch the
same symbol themselves — the closer-scoped patch wins.

The mocked payload satisfies both:
  - Ollama ``/api/tags``:   ``{"models": [{"name": "...", "model": "..."}]}``
  - LM Studio ``/v1/models``: ``{"object": "list", "data": [{"id": "..."}]}``
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _default_probe_payload() -> dict[str, Any]:
    """Happy-path response body for both Ollama /api/tags and LM Studio /v1/models."""
    return {
        # Ollama /api/tags shape
        "models": [
            {"name": "qwen3:4b", "model": "qwen3:4b"},
            {"name": "mistral:7b", "model": "mistral:7b"},
        ],
        # LM Studio /v1/models shape
        "object": "list",
        "data": [
            {"id": "qwen3:4b", "object": "model"},
            {"id": "mistral:7b", "object": "model"},
        ],
    }


def _make_pyreqwest_client_builder(payload: dict[str, Any]) -> MagicMock:
    """Return a MagicMock that satisfies the pyreqwest ClientBuilder call chain.

    Chain under test:
        async with ClientBuilder().timeout(...).error_for_status(True).build() as client:
            resp = await client.get(url).build().send()
            data = await resp.json()

    Each step in the chain must return the right mock type.
    """
    # response mock: resp.json() is a coroutine
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)

    # request mock: .build().send() chain
    request_mock = MagicMock()
    request_mock.send = AsyncMock(return_value=response)

    # request builder: .build() returns request_mock
    request_builder = MagicMock()
    request_builder.build = MagicMock(return_value=request_mock)

    # async context manager client: client.get(url) returns request_builder
    client = AsyncMock()
    client.get = MagicMock(return_value=request_builder)

    # async context manager that yields client
    @asynccontextmanager
    async def _cm(*_args: Any, **_kwargs: Any) -> AsyncGenerator[AsyncMock]:
        yield client

    # builder chain: ClientBuilder().timeout(...).error_for_status(...).build()
    # returns an async context manager
    builder_instance = MagicMock()
    builder_instance.timeout = MagicMock(return_value=builder_instance)
    builder_instance.error_for_status = MagicMock(return_value=builder_instance)
    builder_instance.build = MagicMock(return_value=_cm())

    builder_class = MagicMock(return_value=builder_instance)
    return builder_class


@pytest.fixture(autouse=True)
def _stub_local_provider_probes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Auto-stub pyreqwest.ClientBuilder for every integration test.

    Tests that opt out by re-monkeypatching ``pyreqwest.client.ClientBuilder``
    will see their patch override this one (the closer-scoped patch wins).
    Tests that need the real network call can request the
    ``unmocked_pyreqwest`` fixture to skip this stub.
    """
    if "unmocked_pyreqwest" in request.fixturenames:
        yield
        return
    payload = _default_probe_payload()
    builder_class = _make_pyreqwest_client_builder(payload)
    # Patch at both import sites so whichever the provider imported wins.
    with (
        patch("pyreqwest.client.ClientBuilder", builder_class),
        patch("app.llm.providers.ollama.ClientBuilder", builder_class),
        patch("app.llm.providers.lmstudio.ClientBuilder", builder_class),
    ):
        yield


@pytest.fixture
def unmocked_pyreqwest() -> None:
    """Marker fixture — request to skip the autouse probe stub."""
    return None
