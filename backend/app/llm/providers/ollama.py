"""Ollama provider — wraps ``langchain_ollama.ChatOllama`` with dynamic discovery.

Implements :class:`app.llm.base.LLMProvider` structurally (no inheritance —
the Protocol is ``@runtime_checkable`` and satisfied via duck typing).

Behaviour notes:

- ``bind_tools`` constructs ``ChatOllama(..., reasoning=<bool>)`` where
  ``reasoning`` is decided at bind-time based on whether the configured model
  name matches one of ``Settings.ollama_reasoning_model_prefixes``. qwen3 and
  deepseek-r1 emit thinking tokens; mistral / llama3 / most others do not.
  Passing ``reasoning=True`` to a non-thinking model yields HTTP 400 from the
  daemon (``'"<model>" does not support thinking'``) — this gating prevents
  that. ``app.chat.ChatService.chat_stream`` consumes the optional reasoning
  field via ``chunk.additional_kwargs["reasoning_content"]`` regardless;
  non-thinking models simply produce no thinking SSE events.

- **Pitfall 7 (RESEARCH.md):** reasoning tokens are an Ollama-only concern in
  Phase 4.5. The :class:`app.llm.base.LLMProvider` Protocol intentionally
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
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from app.llm.base import LLMProvider  # noqa: F401  # imported for Wave 2 explicit subclassing
from app.llm.errors import ProbeError, ProbeErrorCode


class OllamaProvider(LLMProvider):
    """Local Ollama provider with dynamic ``/api/tags`` discovery.

    Phase 5 D-03: explicitly subclasses :class:`app.llm.base.LLMProvider`
    (the ABC); the four abstract methods below match the ABC contract.

    The constructor takes its full configuration as arguments — no
    ``app.config.settings`` import — so the factory can hand in either the
    payload-derived ``base_url`` or the ``Settings`` fallback per D-08.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        probe_timeout_seconds: float,
        reasoning_model_prefixes: tuple[str, ...] = ("qwen3", "deepseek-r1"),
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._probe_timeout = probe_timeout_seconds
        self._reasoning_model_prefixes = reasoning_model_prefixes

    def _model_supports_reasoning(self) -> bool:
        """Whether the configured model emits thinking tokens.

        Ollama's wire protocol surfaces ``reasoning=True`` as an unconditional
        request to receive thinking-token output; daemons reject the request
        with HTTP 400 when the model does not support it. We match the model
        name (``qwen3:4b``, ``deepseek-r1:8b``, …) against the configured
        prefix list — same approach OpenAI uses for their o-series detection.
        """
        return any(self._model.startswith(prefix) for prefix in self._reasoning_model_prefixes)

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

    def bind_tools(self, tools: Sequence[BaseTool]) -> Any:
        """Construct a tool-bound runnable that streams via ``ChatOllama``.

        ``reasoning=`` is gated on ``_model_supports_reasoning()`` — we only
        request thinking tokens for models whose name matches the configured
        reasoning-prefix list (qwen3, deepseek-r1, …). Models without that
        capability would have the daemon reject the request with HTTP 400,
        so we just don't ask in the first place. See module docstring +
        Pitfall 7.

        Wave 2 / Plan 05-03 replaces the body of this method with
        ``build_agent`` (returning a PydanticAI ``Agent``). The current
        return-type annotation is ``Any`` so the module imports cleanly
        mid-wave; the LangChain body itself stays in place until Wave 2
        rewrites it.
        """
        llm = ChatOllama(
            model=self._model,
            base_url=self._base_url,
            reasoning=self._model_supports_reasoning(),
        )
        # The explicit ``Any`` return-type annotation here is a transitional
        # knob — Wave 2 swaps this method for ``build_agent`` returning
        # ``pydantic_ai.Agent``.
        return llm.bind_tools(list(tools))

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Any:
        """Wave 2 stub — Plan 05-03 replaces the body with the real PydanticAI implementation.

        Required to satisfy the :class:`app.llm.base.LLMProvider` ABC contract so
        ``OllamaProvider`` is instantiable mid-wave. The Phase 4.5 ``bind_tools``
        path above continues to serve ``ChatService`` until Wave 3.

        Raises:
            NotImplementedError: Always, until Plan 05-03 lands the body.
        """
        raise NotImplementedError("OllamaProvider.build_agent is implemented in Wave 2 / Plan 05-03")
