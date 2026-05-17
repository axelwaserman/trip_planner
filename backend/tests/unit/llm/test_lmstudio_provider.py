"""Unit tests for :class:`app.llm.providers.lmstudio.LMStudioProvider`.

Mirrors :mod:`backend.tests.unit.llm.test_ollama_provider` (the sibling local
provider) — each test corresponds to one of the validate_config / list_models
branches. The wire shape differs from Ollama:

- Ollama:    {"models": [{"name": ..., "model": ...}]}  → /api/tags
- LM Studio: {"object": "list", "data": [{"id": ..., "object": "model"}]} → /v1/models

httpx is mocked at the boundary via ``unittest.mock.patch`` (RESEARCH.md
§"Open Question 2 RESOLVED" — no respx, no pytest_httpx). All tests run
without a live LM Studio daemon.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.errors import ProbeErrorCode
from app.llm.providers.lmstudio import LMStudioProvider

pytestmark = pytest.mark.unit


def _make_provider(model: str = "qwen2.5-coder-7b") -> LMStudioProvider:
    """Construct an LMStudioProvider with deterministic test config."""
    return LMStudioProvider(
        model=model,
        base_url="http://localhost:1234/v1",
        probe_timeout_seconds=1.0,
    )


def _mock_lmstudio_models_response(model_ids: list[str]) -> MagicMock:
    """Build a MagicMock httpx.Response for the LM Studio models endpoint.

    Matches the OpenAI-compatible shape verified live in RESEARCH.md
    §"LM Studio Discovery": ``{"object": "list", "data": [{"id": "<id>",
    "object": "model"}]}``.
    """
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "object": "list",
        "data": [{"id": mid, "object": "model"} for mid in model_ids],
    }
    response.raise_for_status = MagicMock(return_value=None)
    return response


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
    assert "LM Studio" in result.message
    assert "http://localhost:1234/v1" in result.message
    assert "lms server start" in result.hint


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
    assert "LM Studio" in result.message


async def test_validate_config_returns_unreachable_on_http_status_error() -> None:
    """``httpx.HTTPStatusError`` (e.g. 5xx from daemon) → ``PROVIDER_UNREACHABLE``."""
    # Arrange
    provider = _make_provider()
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 503

    # Act
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=httpx.HTTPStatusError("server error", request=request, response=response)),
    ):
        result = await provider.validate_config()

    # Assert
    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE


async def test_validate_config_returns_model_not_installed_when_id_missing() -> None:
    """``/v1/models`` 200 but does not list the requested id → ``MODEL_NOT_INSTALLED``."""
    # Arrange
    provider = _make_provider(model="qwen2.5-coder-7b")
    response = _mock_lmstudio_models_response(["other-7b"])

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
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
    response = _mock_lmstudio_models_response(["qwen2.5-coder-7b", "gpt-oss-20b"])

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
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
    response = _mock_lmstudio_models_response(["b-model", "a-model", "b-model"])

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
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
    malformed = MagicMock(spec=httpx.Response)
    malformed.status_code = 200
    malformed.json.return_value = {"unexpected": "shape"}
    malformed.raise_for_status = MagicMock(return_value=None)

    # Act
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=malformed)):
        models = await provider.list_models()

    # Assert
    assert models == []
