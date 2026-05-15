"""Tests for ``probe_provider()`` covering F1-F4 cases from the UI-SPEC:

* ``provider_unreachable`` — connect error or timeout to the LLM provider
* ``model_not_installed`` — Ollama responds but does not list the requested model
* (success) — Ollama responds and lists the requested model → returns ``None``
* ``missing_api_key`` — cloud provider selected but no API key in settings
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.provider_probe import ProbeErrorCode, probe_provider

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ollama_tags_response(model_names: list[str]) -> MagicMock:
    """Build a mock httpx.Response that mimics the Ollama /api/tags shape."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"models": [{"name": name, "model": name} for name in model_names]}
    response.raise_for_status = MagicMock()
    return response


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


async def test_probe_ollama_unreachable_on_connect_error() -> None:
    """probe_provider returns ``provider_unreachable`` when the daemon refuses connection."""
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE


async def test_probe_ollama_model_not_installed() -> None:
    """probe_provider returns ``model_not_installed`` when the requested tag is missing."""
    mock_response = _mock_ollama_tags_response(["other:7b"])
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is not None
    assert result.error == ProbeErrorCode.MODEL_NOT_INSTALLED
    assert "ollama pull qwen3:4b" in result.hint


async def test_probe_ollama_success() -> None:
    """probe_provider returns ``None`` when the model is installed and reachable."""
    mock_response = _mock_ollama_tags_response(["qwen3:4b"])
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is None


async def test_probe_cloud_missing_key() -> None:
    """probe_provider returns ``missing_api_key`` when openai_api_key is not set."""
    # Patch the settings.openai_api_key to None so probe sees no credential.
    with patch("app.config.settings.openai_api_key", None, create=True):
        result = await probe_provider("openai", "gpt-4o-mini")

    assert result is not None
    assert result.error == ProbeErrorCode.MISSING_API_KEY
    assert "OPENAI_API_KEY" in result.hint


async def test_probe_ollama_timeout() -> None:
    """probe_provider returns ``provider_unreachable`` when the request times out."""
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
    ):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is not None
    assert result.error == ProbeErrorCode.PROVIDER_UNREACHABLE
