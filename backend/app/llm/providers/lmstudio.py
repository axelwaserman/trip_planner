"""LM Studio provider — wraps :class:`langchain_openai.ChatOpenAI` against a local LM Studio daemon.

Implements :class:`app.llm.base.LLMProvider` structurally (no inheritance —
the Protocol is ``@runtime_checkable`` and satisfied via duck typing). Peer of
:class:`app.llm.providers.ollama.OllamaProvider` (local, dynamic discovery) and
:class:`app.llm.providers.openai.OpenAIProvider` (ChatOpenAI delegate, cloud).

Design notes:

- **D-15 — first-class provider class.** LM Studio is a peer of Ollama / OpenAI /
  Anthropic, not a hidden adapter. The factory match block (Plan 06 + 04b)
  dispatches ``"lmstudio"`` to this class.

- **D-16 — ChatOpenAI delegation.** LM Studio exposes an OpenAI-compatible REST
  surface; the provider re-uses :class:`langchain_openai.ChatOpenAI` with a
  custom ``base_url`` pointing at the local daemon. No second SDK dependency.

- **D-17 — no API key in v1.** The provider's ``__init__`` does NOT accept an
  ``api_key``. The sentinel string ``"lm-studio"`` is mandatory at
  ``ChatOpenAI`` construction (the OpenAI SDK validator rejects empty/None
  api_key — RESEARCH.md Pitfall 3) but it is never sent to ``api.openai.com``
  because ``base_url`` overrides the destination. Settings has NO
  ``lmstudio_api_key`` field for the same reason.

- **D-18 — discovery via GET ${base_url}/models.** ``list_models`` hits the
  OpenAI-compatible ``/models`` endpoint (the daemon's ``/v1`` prefix is
  already part of ``base_url``) and parses
  ``{"object": "list", "data": [{"id": "<model>", ...}]}`` defensively.
  Returns ``[]`` on shape drift (RESEARCH.md Assumption A4 — empty-list
  fallback rather than raising).

- **Configuration injection.** The provider does NOT import
  :mod:`app.config` — all knobs (``model``, ``base_url``,
  ``probe_timeout_seconds``) arrive via ``__init__``. The factory wires
  :attr:`Settings.lmstudio_base_url` and
  :attr:`Settings.provider_probe_timeout_seconds` when the session payload's
  ``base_url`` is ``None``. Mirrors the OllamaProvider precedent.

Cross-reference: :meth:`bind_tools` is structurally symmetric with
:meth:`app.llm.providers.openai.OpenAIProvider.bind_tools` — only the
``base_url`` and the sentinel ``api_key`` differ.
"""

from collections.abc import Sequence
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.llm.base import LLMProvider  # noqa: F401  # imported for Wave 2 explicit subclassing
from app.llm.errors import ProbeError, ProbeErrorCode


class LMStudioProvider(LLMProvider):
    """Local LM Studio provider with dynamic ``${base_url}/models`` discovery.

    Phase 5 D-03: explicitly subclasses :class:`app.llm.base.LLMProvider`
    (the ABC); the four abstract methods below match the ABC contract.

    The constructor takes its full configuration as arguments — no
    :mod:`app.config` import — so the factory hands in either the payload's
    ``base_url`` or the :attr:`Settings.lmstudio_base_url` fallback per D-08
    (applied symmetrically to local providers).
    """

    def __init__(self, model: str, base_url: str, probe_timeout_seconds: float) -> None:
        """Construct with model id, daemon base URL, and probe timeout.

        Args:
            model: LM Studio model identifier (e.g. ``"qwen2.5-coder-7b"``).
                Per D-18 the value is whatever the daemon returned from a
                prior dynamic discovery call — NOT a curated allow-list.
            base_url: LM Studio daemon URL including the ``/v1`` prefix
                (e.g. ``"http://localhost:1234/v1"``). The factory injects
                either the request payload's value or
                :attr:`Settings.lmstudio_base_url`.
            probe_timeout_seconds: Per-request httpx timeout for
                :meth:`list_models` and :meth:`validate_config`. Sourced
                from :attr:`Settings.provider_probe_timeout_seconds` —
                same knob as the Ollama provider.
        """
        self._model = model
        self._base_url = base_url
        self._probe_timeout = probe_timeout_seconds

    def get_provider_name(self) -> str:
        """Return the wire-level provider literal."""
        return "lmstudio"

    async def validate_config(self) -> ProbeError | None:
        """Probe the LM Studio daemon for reachability + model presence.

        Returns ``ProbeError(error=PROVIDER_UNREACHABLE, ...)`` on connect /
        timeout / non-2xx HTTP, ``ProbeError(error=MODEL_NOT_INSTALLED, ...)``
        when the daemon responds but does not list ``self._model``, otherwise
        ``None``.

        Wire copy mirrors :meth:`OllamaProvider.validate_config` —
        ``"Ollama"`` swapped for ``"LM Studio"``, ``"ollama serve"`` swapped
        for ``"LM Studio (`lms server start`)"``.
        """
        try:
            available = await self.list_models()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return ProbeError(
                error=ProbeErrorCode.PROVIDER_UNREACHABLE,
                message=f"Can't reach LM Studio at {self._base_url}.",
                hint="Start LM Studio (`lms server start`) and retry, or pick another provider.",
            )
        if self._model not in available:
            return ProbeError(
                error=ProbeErrorCode.MODEL_NOT_INSTALLED,
                message=f"LM Studio is running but {self._model} isn't loaded.",
                hint=f"Load `{self._model}` in LM Studio or pick a different model.",
            )
        return None

    async def list_models(self) -> list[str]:
        """Return sorted unique model ids from the LM Studio daemon's ``/models``.

        The full URL is ``{base_url}/models``; ``base_url`` already includes
        the ``/v1`` prefix (e.g. ``http://localhost:1234/v1``), so the
        constructed URL targets the OpenAI-compatible models endpoint.

        Defensively parses the OpenAI-compatible response shape
        ``{"object": "list", "data": [{"id": "<model>", "object": "model", ...}]}``
        per RESEARCH.md §"LM Studio Discovery". Returns ``[]`` on shape drift
        (Assumption A4) — non-list ``data`` field, missing ``id`` keys, or
        non-dict entries are filtered out rather than raising.
        """
        url = f"{self._base_url.rstrip('/')}/models"
        async with httpx.AsyncClient(timeout=self._probe_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
        payload = response.json()
        # LM Studio models endpoint shape: {"object": "list", "data": [{"id": "...", "object": "model", ...}]}
        # Defensive parse — Assumption A4 — empty list on shape drift.
        data = payload.get("data", [])
        if not isinstance(data, list):
            return []
        return sorted({entry["id"] for entry in data if isinstance(entry, dict) and entry.get("id")})

    def bind_tools(self, tools: Sequence[BaseTool]) -> Any:
        """Construct a tool-bound runnable that streams from the LM Studio daemon.

        Constructs ``ChatOpenAI(model=..., base_url=self._base_url,
        api_key="lm-studio")`` — the sentinel ``api_key`` is MANDATORY
        (RESEARCH.md Pitfall 3 — the OpenAI SDK rejects empty/None api_key
        at construction). Because ``base_url`` overrides the destination,
        the sentinel never reaches ``api.openai.com``.

        Wave 2 / Plan 05-03 replaces this method with ``build_agent`` returning
        a PydanticAI ``Agent``; the return-type annotation is ``Any`` here so
        the module imports cleanly mid-wave.
        """
        # ChatOpenAI types ``api_key`` as ``SecretStr | Callable | None``; the
        # sentinel literal must be wrapped to satisfy mypy strict. The literal
        # text "lm-studio" still appears in source for grep-based traceability
        # to D-17 / RESEARCH.md Pitfall 3.
        llm = ChatOpenAI(
            model=self._model,
            base_url=self._base_url,
            api_key=SecretStr("lm-studio"),  # sentinel; D-17, RESEARCH.md Pitfall 3
        )
        # The explicit ``Any`` return-type annotation here is the transitional
        # knob until Wave 2 swaps this method for ``build_agent``.
        return llm.bind_tools(list(tools))

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Any:
        """Wave 2 stub — Plan 05-03 replaces the body with the real PydanticAI implementation.

        Required to satisfy the :class:`app.llm.base.LLMProvider` ABC contract so
        ``LMStudioProvider`` is instantiable mid-wave. The Phase 4.5 ``bind_tools``
        path above continues to serve ``ChatService`` until Wave 3.

        Raises:
            NotImplementedError: Always, until Plan 05-03 lands the body.
        """
        raise NotImplementedError("LMStudioProvider.build_agent is implemented in Wave 2 / Plan 05-03")
