"""Unit tests for :class:`app.llm.providers.lmstudio.LMStudioProvider`.

Mirrors :mod:`backend.tests.unit.llm.test_ollama_provider` (the sibling local
provider) — each test corresponds to one of the validate_config / list_models
branches. The wire shape differs from Ollama:

- Ollama:    {"models": [{"name": ..., "model": ...}]}  → /api/tags
- LM Studio: {"object": "list", "data": [{"id": ..., "object": "model"}]} → /v1/models

H1/H4 (Plan 05-07): httpx replaced with pyreqwest (ADR-008). Tests now mock
``pyreqwest.client.ClientBuilder`` at the provider module level rather than
``httpx.AsyncClient.get``. All tests run without a live LM Studio daemon.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from pyreqwest.exceptions import CauseErrorDetails, ConnectError, RequestTimeoutError, StatusError, StatusErrorDetails

from app.llm.errors import ProbeErrorCode
from app.llm.providers.lmstudio import LMStudioProvider


def _make_provider(model: str = "qwen2.5-coder-7b") -> LMStudioProvider:
    """Construct an LMStudioProvider with deterministic test config."""
    return LMStudioProvider(
        model=model,
        base_url="http://localhost:1234/v1",
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
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE
    assert "LM Studio" in result.message
    assert "http://localhost:1234/v1" in result.message
    assert "lms server start" in result.hint


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
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE
    assert "LM Studio" in result.message


async def test_validate_config_returns_unreachable_on_status_error() -> None:
    """StatusError (e.g. 5xx from daemon) → ``PROVIDER_UNREACHABLE``."""
    # Arrange
    provider = _make_provider()
    builder = MagicMock()
    builder.timeout.return_value = builder
    builder.error_for_status.return_value = builder
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(side_effect=StatusError("503 server error", StatusErrorDetails()))
    ctx_manager.__aexit__ = AsyncMock(return_value=None)
    builder.build.return_value = ctx_manager

    # Act
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE


async def test_validate_config_returns_model_not_installed_when_id_missing() -> None:
    """``/v1/models`` 200 but does not list the requested id → ``MODEL_NOT_INSTALLED``."""
    # Arrange
    provider = _make_provider(model="qwen2.5-coder-7b")
    payload = {
        "object": "list",
        "data": [{"id": "other-7b", "object": "model"}],
    }
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MODEL_NOT_INSTALLED
    assert "qwen2.5-coder-7b" in result.message
    assert "qwen2.5-coder-7b" in result.hint


async def test_validate_config_returns_none_when_model_present() -> None:
    """``/v1/models`` lists the requested id → ``validate_config`` returns ``None``."""
    # Arrange
    provider = _make_provider(model="qwen2.5-coder-7b")
    payload = {
        "object": "list",
        "data": [
            {"id": "qwen2.5-coder-7b", "object": "model"},
            {"id": "gpt-oss-20b", "object": "model"},
        ],
    }
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        result = await provider.validate_config()

    # Assert
    assert result is None


async def test_list_models_returns_sorted_unique_ids_from_v1_models() -> None:
    """``LMStudioProvider.list_models`` returns sorted, deduped ids from the daemon.

    Covers the dynamic-discovery success criterion (REQ-llm-provider-abstraction)
    plus the dedupe contract — duplicate ids in the response collapse to a
    single entry, output is alphabetically sorted.
    """
    # Arrange — duplicate "b-model" intentionally to exercise dedupe.
    provider = _make_provider()
    payload = {
        "object": "list",
        "data": [
            {"id": "b-model", "object": "model"},
            {"id": "a-model", "object": "model"},
            {"id": "b-model", "object": "model"},
        ],
    }
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        models = await provider.list_models()

    # Assert
    assert models == ["a-model", "b-model"]


async def test_list_models_returns_empty_list_on_malformed_shape() -> None:
    """Defensive fallback (RESEARCH.md Assumption A4): unknown shape → ``[]``.

    When the daemon returns a 200 OK but the JSON body lacks the expected
    ``{"data": [...]}`` envelope (e.g. shape drift on a future LM Studio
    release), ``list_models`` returns ``[]`` rather than raising. This
    matches the Ollama provider's defensive parse philosophy.
    """
    # Arrange
    provider = _make_provider()
    payload = {"unexpected": "shape"}
    builder = _make_pyreqwest_client_mock(json_payload=payload)

    # Act
    with patch("app.llm.providers.lmstudio.ClientBuilder", return_value=builder):
        models = await provider.list_models()

    # Assert
    assert models == []
