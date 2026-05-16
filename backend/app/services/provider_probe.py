"""Provider health probe — runs at session-create to surface F1-F4 errors early.

D-07 + D-18 (CONTEXT.md): probe proactively at session-create time, not lazily
on first chat send. The probe returns ``None`` on success or a structured
:class:`ProbeError` mapping 1:1 to the UI-SPEC F1-F4 taxonomy.
"""

from enum import StrEnum

import httpx
from pydantic import BaseModel

from app.config import settings


class ProbeErrorCode(StrEnum):
    """Wire-level taxonomy shared by :class:`ProbeError` and ``SessionCreateError``.

    A single source of truth for the F1-F3 codes the frontend's
    ``mapProbeError`` consumes. ``provider_unreachable`` covers any provider's
    network-level failure (currently only Ollama issues live HTTP, but the
    symbol stays generic so future cloud probes plug in without a rename).
    """

    PROVIDER_UNREACHABLE = "provider_unreachable"
    MODEL_NOT_INSTALLED = "model_not_installed"
    MISSING_API_KEY = "missing_api_key"


class ProbeError(BaseModel):
    """Structured probe failure — maps to UI-SPEC F1/F2/F3."""

    error: ProbeErrorCode
    message: str
    hint: str


async def probe_provider(provider: str, model: str) -> ProbeError | None:
    """Return ``None`` if the provider is usable, otherwise a structured ``ProbeError``.

    Args:
        provider: One of ``"ollama"``, ``"openai"``, ``"anthropic"``.
        model: Model identifier (e.g., ``"qwen3:4b"``, ``"gpt-4o-mini"``).

    Returns:
        ``None`` on success, :class:`ProbeError` on failure. Unknown providers
        return ``None`` — the existing 400 path in ``routes.py`` already
        rejects them before reaching the probe.
    """
    if provider == "ollama":
        return await _probe_ollama(model)
    if provider in {"openai", "anthropic"}:
        return _probe_cloud(provider)
    return None


async def _probe_ollama(model: str) -> ProbeError | None:
    """Probe the Ollama daemon for reachability + model presence.

    Returns ``ProbeError(error=PROVIDER_UNREACHABLE, ...)`` on connect/timeout
    or non-2xx, ``ProbeError(error=MODEL_NOT_INSTALLED, ...)`` when the
    daemon responds but does not list ``model``, otherwise ``None``.
    """
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=settings.provider_probe_timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        return ProbeError(
            error=ProbeErrorCode.PROVIDER_UNREACHABLE,
            message=f"Can't reach Ollama at {settings.ollama_base_url}.",
            hint="Run `ollama serve` and retry, or pick another provider.",
        )

    payload = response.json()
    # Ollama /api/tags shape: { "models": [ { "name": "...", "model": "...", ... }, ... ] }
    # Match on `name` AND `model` to be robust to minor shape drift (A3).
    models_list = payload.get("models", [])
    available = {entry.get("name") for entry in models_list} | {entry.get("model") for entry in models_list}
    if model not in available:
        return ProbeError(
            error=ProbeErrorCode.MODEL_NOT_INSTALLED,
            message=f"Ollama is running but {model} isn't installed.",
            hint=f"Run `ollama pull {model}` or pick a different model.",
        )
    return None


def _probe_cloud(provider: str) -> ProbeError | None:
    """Verify the cloud provider's API key is configured.

    v1: env-var presence only. Phase 4.5 ships live key validation.
    """
    key = getattr(settings, f"{provider}_api_key", None)
    if not key:
        env_var = f"{provider.upper()}_API_KEY"
        return ProbeError(
            error=ProbeErrorCode.MISSING_API_KEY,
            message=f"{provider.title()} needs an API key.",
            hint=f"Set {env_var} on the backend and restart.",
        )
    return None
