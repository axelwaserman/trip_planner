"""Ollama provider — wraps ``langchain_ollama.ChatOllama`` with dynamic discovery.

Implements :class:`app.llm.protocol.LLMProvider` structurally (no inheritance —
the Protocol is ``@runtime_checkable`` and satisfied via duck typing).

Behaviour notes:

- ``bind_tools`` constructs ``ChatOllama(..., reasoning=True)`` so qwen3 thinking
  tokens continue to flow into ``chunk.additional_kwargs["reasoning_content"]``
  downstream. ``app.chat.ChatService.chat_stream`` consumes that key and emits
  ``thinking`` SSE events from it. This wiring preserves the production
  behaviour in ``app/api/main.py:41`` where ``init_chat_model(..., reasoning=True)``
  is invoked today.

- **Pitfall 7 (RESEARCH.md):** reasoning tokens are an Ollama-only concern in
  Phase 4.5. The :class:`app.llm.protocol.LLMProvider` Protocol intentionally
  does **NOT** abstract reasoning. Cloud providers (OpenAI/Anthropic) do not
  emit ``reasoning_content``; abstracting it across providers would force
  shape-faking we don't want.

- **Pitfall 4 (RESEARCH.md):** Ollama's ``/api/tags`` payload has historically
  drifted between minor versions — some daemons populate ``entry["name"]`` only,
  others ``entry["model"]`` only, others both. ``list_models`` defensively
  unions both fields so the implementation tolerates that drift. The 4.2
  ``provider_probe._probe_ollama`` shipped this exact pattern; we preserve it
  verbatim here.

- **Configuration injection:** the provider does NOT import ``app.config`` —
  all knobs (``model``, ``base_url``, ``probe_timeout_seconds``) are passed
  via ``__init__``. The factory (Plan 06) is responsible for wiring
  ``Settings.ollama_base_url`` / ``Settings.provider_probe_timeout_seconds``
  into the constructor when the session payload's ``base_url`` is ``None``.
  This keeps the provider trivially testable and matches CLAUDE.md's
  "tunable thresholds live on Settings" rule by leaving the Settings
  ownership upstream of the provider class.
"""

from collections.abc import Sequence

import httpx
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from app.llm.errors import ProbeError, ProbeErrorCode
from app.llm.protocol import BoundProvider


class OllamaProvider:
    """Local Ollama provider with dynamic ``/api/tags`` discovery.

    Satisfies :class:`app.llm.protocol.LLMProvider` structurally; the four
    members below match the Protocol signatures exactly.

    The constructor takes its full configuration as arguments — no
    ``app.config.settings`` import — so the factory can hand in either the
    payload-derived ``base_url`` or the ``Settings`` fallback per D-08.
    """

    def __init__(self, model: str, base_url: str, probe_timeout_seconds: float) -> None:
        self._model = model
        self._base_url = base_url
        self._probe_timeout = probe_timeout_seconds

    def get_provider_name(self) -> str:
        return "ollama"

    async def validate_config(self) -> ProbeError | None:
        """Probe the Ollama daemon for reachability + model presence.

        Returns ``ProbeError(error=PROVIDER_UNREACHABLE, ...)`` on connect/timeout
        or non-2xx HTTP status, ``ProbeError(error=MODEL_NOT_INSTALLED, ...)``
        when the daemon responds but does not list ``self._model``, otherwise
        ``None``.

        Wire copy (message + hint) is preserved verbatim from the 4.2
        ``app.services.provider_probe._probe_ollama`` body — only the
        ``settings.ollama_base_url`` substitution differs (``self._base_url``).
        """
        try:
            available = await self.list_models()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return ProbeError(
                error=ProbeErrorCode.PROVIDER_UNREACHABLE,
                message=f"Can't reach Ollama at {self._base_url}.",
                hint="Run `ollama serve` and retry, or pick another provider.",
            )
        if self._model not in available:
            return ProbeError(
                error=ProbeErrorCode.MODEL_NOT_INSTALLED,
                message=f"Ollama is running but {self._model} isn't installed.",
                hint=f"Run `ollama pull {self._model}` or pick a different model.",
            )
        return None

    async def list_models(self) -> list[str]:
        """Return sorted unique model ids from the Ollama daemon's ``/api/tags``.

        Defensively unions ``entry["name"]`` and ``entry["model"]`` because
        Ollama wire-shape has historically varied between versions — see
        Pitfall 4 in RESEARCH.md. Empty/None values in either field are
        dropped by the comprehension's truthiness guard.
        """
        url = f"{self._base_url.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=self._probe_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
        payload = response.json()
        # Ollama /api/tags shape: { "models": [ { "name": "...", "model": "...", ... }, ... ] }
        # Match on `name` AND `model` to be robust to minor shape drift (Pitfall 4).
        models_list = payload.get("models", [])
        available = {entry.get("name") for entry in models_list if entry.get("name")} | {
            entry.get("model") for entry in models_list if entry.get("model")
        }
        return sorted(available)

    def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider:
        """Construct a tool-bound runnable that streams via ``ChatOllama``.

        ``reasoning=True`` keeps qwen3 thinking tokens flowing through
        ``chunk.additional_kwargs["reasoning_content"]`` — see module docstring
        and Pitfall 7. The returned ``Runnable[LanguageModelInput, AIMessage]``
        structurally satisfies :class:`BoundProvider` (it has ``ainvoke`` +
        ``astream``); mypy can't statically verify that match because LangChain's
        ``Runnable`` is a generic class, not a Protocol — hence the targeted
        ``type: ignore``.
        """
        llm = ChatOllama(
            model=self._model,
            base_url=self._base_url,
            reasoning=True,  # qwen3 thinking tokens — preserves api/main.py:41 behaviour
        )
        # mypy can't statically prove Runnable[LanguageModelInput, AIMessage]
        # matches the BoundProvider Protocol; @runtime_checkable confirms it
        # at runtime via the conformance test (Plan 06).
        return llm.bind_tools(list(tools))  # type: ignore[return-value]
