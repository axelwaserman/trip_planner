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
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.errors import ProbeErrorCode
from app.llm.providers.ollama import OllamaProvider

pytestmark = pytest.mark.unit


def _make_provider(model: str = "qwen3:4b") -> OllamaProvider:
    """Construct an OllamaProvider with deterministic test config."""
    return OllamaProvider(
        model=model,
        base_url="http://localhost:11434",
        probe_timeout_seconds=1.0,
    )


async def test_validate_config_returns_unreachable_on_connect_error() -> None:
    """ConnectError from ``httpx.AsyncClient.get`` → ``PROVIDER_UNREACHABLE``."""
    # Arrange
    provider = _make_provider()

    # Act
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=httpx.ConnectError("refused")),
    ):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE
    assert "Ollama" in result.message
    assert "http://localhost:11434" in result.message


async def test_validate_config_returns_unreachable_on_timeout() -> None:
    """``httpx.TimeoutException`` → ``PROVIDER_UNREACHABLE``."""
    # Arrange
    provider = _make_provider()

    # Act
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
    ):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE


async def test_validate_config_returns_model_not_installed_when_tag_missing(
    mock_ollama_tags_response: object,
) -> None:
    """``/api/tags`` 200 but does not list the requested model → ``MODEL_NOT_INSTALLED``."""
    # Arrange
    provider = _make_provider(model="qwen3:4b")
    build_response = mock_ollama_tags_response  # factory fixture
    response = build_response(["other:7b"])  # type: ignore[operator]

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.MODEL_NOT_INSTALLED
    assert "qwen3:4b" in result.message
    assert "ollama pull qwen3:4b" in result.hint


async def test_validate_config_returns_none_when_model_present(
    mock_ollama_tags_response: object,
) -> None:
    """``/api/tags`` lists the requested model → ``validate_config`` returns ``None``."""
    # Arrange
    provider = _make_provider(model="qwen3:4b")
    build_response = mock_ollama_tags_response
    response = build_response(["qwen3:4b"])  # type: ignore[operator]

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        result = await provider.validate_config()

    # Assert
    assert result is None


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
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "models": [
            {"name": "b", "model": "b"},
            {"name": "a", "model": "a"},
            {"name": "c", "model": "x"},  # divergent: name=c, model=x
        ]
    }
    response.raise_for_status = MagicMock()

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        models = await provider.list_models()

    # Assert — sorted union of name + model fields.
    assert models == ["a", "b", "c", "x"]
