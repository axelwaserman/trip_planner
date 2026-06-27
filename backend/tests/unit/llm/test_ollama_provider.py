"""Unit tests for :class:`app.llm.providers.ollama.OllamaProvider`.

Mirrors ``backend/tests/unit/test_provider_probe.py`` (the 4.2 analog) — each
test corresponds to one of the 4.2 ``probe_provider("ollama", ...)`` cases,
lifted onto the new ``OllamaProvider.validate_config()`` member, plus one new
``list_models`` test for the dynamic-discovery success criterion
(REQ-llm-provider-abstraction).

Per RESEARCH.md §"Pattern 1": ``OllamaProvider.bind_tools`` returns a runnable
that satisfies the ``BoundProvider`` Protocol; that surface is exercised by the
chat-stream integration tests in Wave 3, NOT here.

The 4.2 ``test_provider_probe.py`` tests remain unchanged — Plan 09 deletes
them once the route layer rewires onto the factory.

H1/H4 (Plan 05-07): httpx replaced with pyreqwest (ADR-008). Tests now mock
``pyreqwest.client.ClientBuilder`` at the provider module level rather than
``httpx.AsyncClient.get``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from pyreqwest.exceptions import CauseErrorDetails, ConnectError, RequestTimeoutError

from app.llm.errors import ProbeErrorCode
from app.llm.providers.ollama import OllamaProvider


def _make_provider(model: str = "qwen3:4b") -> OllamaProvider:
    """Construct an OllamaProvider with deterministic test config."""
    return OllamaProvider(
        model=model,
        base_url="http://localhost:11434",
        probe_timeout_seconds=1.0,
    )


def _make_pyreqwest_client_mock(json_payload: dict | None = None) -> MagicMock:
    """Build a mock pyreqwest ClientBuilder chain returning ``json_payload``.

    The chain: ClientBuilder().timeout(...).error_for_status(True).build()
    returns an async context manager whose __aenter__ gives a ``client``.
    ``client.get(url).build().send()`` is awaited to get a ``response``.
    ``response.json()`` is awaited to get the payload dict.
    """
    response = AsyncMock()
    response.json = AsyncMock(return_value=json_payload or {})

    send_mock = AsyncMock(return_value=response)
    consumed_request = MagicMock()
    consumed_request.send = send_mock

    request_builder = MagicMock()
    request_builder.build.return_value = consumed_request

    client = MagicMock()
    client.get.return_value = request_builder

    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=client)
    ctx_manager.__aexit__ = AsyncMock(return_value=None)

    builder = MagicMock()
    builder.timeout.return_value = builder
    builder.error_for_status.return_value = builder
    builder.build.return_value = ctx_manager

    return builder


async def test_validate_config_returns_unreachable_on_connect_error() -> None:
    """ConnectError from pyreqwest → ``PROVIDER_UNREACHABLE``."""
    # Arrange
    provider = _make_provider()
    builder = MagicMock()
    builder.timeout.return_value = builder
    builder.error_for_status.return_value = builder
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(side_effect=ConnectError("refused", CauseErrorDetails()))
    ctx_manager.__aexit__ = AsyncMock(return_value=None)
    builder.build.return_value = ctx_manager

    # Act
    with patch("app.llm.providers.ollama.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE
    assert "Ollama" in result.message
    assert "http://localhost:11434" in result.message


async def test_validate_config_returns_unreachable_on_timeout() -> None:
    """RequestTimeoutError from pyreqwest → ``PROVIDER_UNREACHABLE``."""
    # Arrange
    provider = _make_provider()
    builder = MagicMock()
    builder.timeout.return_value = builder
    builder.error_for_status.return_value = builder
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(side_effect=RequestTimeoutError("timed out", CauseErrorDetails()))
    ctx_manager.__aexit__ = AsyncMock(return_value=None)
    builder.build.return_value = ctx_manager

    # Act
    with patch("app.llm.providers.ollama.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE


async def test_validate_config_returns_model_not_installed_when_tag_missing() -> None:
    """``/api/tags`` 200 but does not list the requested model → ``MODEL_NOT_INSTALLED``."""
    # Arrange
    provider = _make_provider(model="qwen3:4b")
    payload = {
        "models": [
            {"name": "other:7b", "model": "other:7b"},
        ]
    }
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.ollama.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MODEL_NOT_INSTALLED
    assert "qwen3:4b" in result.message
    assert "ollama pull qwen3:4b" in result.hint


async def test_validate_config_returns_none_when_model_present() -> None:
    """``/api/tags`` lists the requested model → ``validate_config`` returns ``None``."""
    # Arrange
    provider = _make_provider(model="qwen3:4b")
    payload = {
        "models": [
            {"name": "qwen3:4b", "model": "qwen3:4b"},
        ]
    }
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.ollama.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is None


# NOTE: ``test_model_supports_reasoning_matches_configured_prefixes`` retired in
# Wave 2 / Plan 05-03. The Phase 4.5 ``_model_supports_reasoning`` private method
# and the ``reasoning_model_prefixes`` constructor parameter were both removed —
# PydanticAI's ``OllamaProvider`` inherits ``thinking_tags=('<think>', '</think>')``
# from ``qwen_model_profile`` so the ``<think>`` reasoning tokens parse natively
# without explicit prefix gating (RESEARCH OQ-04). The qwen3 thinking-tags surface
# is now covered by ``tests/unit/llm/providers/test_ollama_thinking.py``.


async def test_list_models_returns_sorted_unique_ids_from_api_tags() -> None:
    """``OllamaProvider.list_models`` returns sorted, deduped model ids from ``/api/tags``.

    Covers the dynamic-discovery success criterion (REQ-llm-provider-abstraction §6).
    Per RESEARCH.md §"Pitfall 4" the implementation must defensively match on BOTH
    ``name`` and ``model`` keys to handle Ollama wire-shape drift. We exercise that
    by setting up an explicit response where ``name`` and ``model`` diverge for one
    entry — the implementation should union both fields.
    """
    # Arrange — construct a mock response with name/model divergence on entry 3.
    provider = _make_provider()
    payload = {
        "models": [
            {"name": "b", "model": "b"},
            {"name": "a", "model": "a"},
            {"name": "c", "model": "x"},  # divergent: name=c, model=x
        ]
    }
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.ollama.ClientBuilder", return_value=builder):
        models = await provider.list_models()

    # Assert — sorted union of name + model fields.
    assert models == ["a", "b", "c", "x"]
