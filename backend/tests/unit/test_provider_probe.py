"""Failing test stubs for ``probe_provider()`` — Plan 02 will create the service.

These stubs cover the four behavioral cases for ``probe_provider`` (F1-F4 in the
UI-SPEC):

* ``ollama_unreachable`` — connect error or timeout to the Ollama daemon
* ``model_not_installed`` — Ollama responds but does not list the requested model
* (success) — Ollama responds and lists the requested model → returns ``None``
* ``missing_api_key`` — cloud provider selected but no API key in settings

The module ``app.services.provider_probe`` does not exist yet; the import is wrapped
in a try/except so collection does not crash. Each test is marked ``xfail`` so the
suite stays green; once Plan 02 lands, they will start passing and the executor must
remove the xfail markers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Conditional import — Plan 02 will create app.services.provider_probe
# ---------------------------------------------------------------------------

# Plan 02 will create app.services.provider_probe; until then the import fails at
# runtime (caught) and at type-check time. We silence the type-check error with a
# narrow ignore — once Plan 02 lands, the ignore becomes unused and mypy will flag
# it, prompting the executor to remove it together with the try/except guard.
try:
    from app.services.provider_probe import probe_provider  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — module does not exist until Plan 02
    probe_provider = None


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


@pytest.mark.xfail(
    strict=False,
    reason="probe_provider() not yet implemented — Plan 02 creates app.services.provider_probe",
)
async def test_probe_ollama_unreachable_on_connect_error() -> None:
    """probe_provider returns ``ollama_unreachable`` when the daemon refuses connection."""
    assert probe_provider is not None  # gate — fails fast if Plan 02 didn't land
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is not None
    assert result.error == "ollama_unreachable"


@pytest.mark.xfail(
    strict=False,
    reason="probe_provider() not yet implemented — Plan 02 creates app.services.provider_probe",
)
async def test_probe_ollama_model_not_installed() -> None:
    """probe_provider returns ``model_not_installed`` when the requested tag is missing."""
    assert probe_provider is not None
    mock_response = _mock_ollama_tags_response(["other:7b"])
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is not None
    assert result.error == "model_not_installed"


@pytest.mark.xfail(
    strict=False,
    reason="probe_provider() not yet implemented — Plan 02 creates app.services.provider_probe",
)
async def test_probe_ollama_success() -> None:
    """probe_provider returns ``None`` when the model is installed and reachable."""
    assert probe_provider is not None
    mock_response = _mock_ollama_tags_response(["qwen3:4b"])
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is None


@pytest.mark.xfail(
    strict=False,
    reason="probe_provider() not yet implemented — Plan 02 creates app.services.provider_probe",
)
async def test_probe_cloud_missing_key() -> None:
    """probe_provider returns ``missing_api_key`` when openai_api_key is not set."""
    assert probe_provider is not None
    # Patch the settings.openai_api_key to None so probe sees no credential.
    with patch("app.config.settings.openai_api_key", None, create=True):
        result = await probe_provider("openai", "gpt-4o-mini")

    assert result is not None
    assert result.error == "missing_api_key"


@pytest.mark.xfail(
    strict=False,
    reason="probe_provider() not yet implemented — Plan 02 creates app.services.provider_probe",
)
async def test_probe_ollama_timeout() -> None:
    """probe_provider returns ``ollama_unreachable`` when the request times out."""
    assert probe_provider is not None
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
    ):
        result = await probe_provider("ollama", "qwen3:4b")

    assert result is not None
    assert result.error == "ollama_unreachable"
