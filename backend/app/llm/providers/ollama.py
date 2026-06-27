"""Ollama provider — wraps PydanticAI's ``OpenAIChatModel`` against an Ollama daemon.

Phase 5 / Plan 05-03 rewrite (Wave 2): the Phase 4.5 LangChain ``bind_tools`` body
retires. :meth:`build_agent` now constructs a ``pydantic_ai.Agent`` backed by
``OpenAIChatModel(model, provider=PaiOllamaProvider(base_url=...))``. PydanticAI's
``OllamaProvider`` inherits ``thinking_tags=('<think>', '</think>')`` from
``qwen_model_profile`` (RESEARCH OQ-04), which is what makes qwen3's native
``<think>`` reasoning tokens parse into ``ThinkingPart`` deltas without any
explicit ``reasoning=True`` flag — so the Phase 4.5 ``_model_supports_reasoning``
prefix gating retires alongside ``Settings.ollama_reasoning_model_prefixes``
(D-12 / RESEARCH OQ-04).

Behaviour notes:

- **Pitfall 4 (RESEARCH.md):** Ollama's ``/api/tags`` payload has historically
  drifted between minor versions — some daemons populate ``entry["name"]`` only,
  others ``entry["model"]`` only, others both. ``list_models`` defensively
  unions both fields so the implementation tolerates that drift. The 4.2
  ``provider_probe._probe_ollama`` shipped this exact pattern; we preserve it
  verbatim here.

- **Configuration injection:** the provider does NOT import ``app.config`` —
  all knobs (``model``, ``base_url``, ``probe_timeout_seconds``) are passed
  via ``__init__``. The factory is responsible for wiring
  ``Settings.ollama_base_url`` / ``Settings.provider_probe_timeout_seconds``
  into the constructor when the session payload's ``base_url`` is ``None``.
  This keeps the provider trivially testable and matches CLAUDE.md's
  "tunable thresholds live on Settings" rule by leaving the Settings
  ownership upstream of the provider class.

- **ADR-008 — pyreqwest per CLAUDE.md.** ``validate_config`` and
  ``list_models`` use ``pyreqwest`` for ``/api/tags`` probes (H1, Phase 07
  fix). The response JSON is consumed inside the ``async with`` block (H4) to
  ensure the context manager is still active when the body is parsed.
"""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider as _PaiOllamaProvider
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, JSONDecodeError, ReadError, RequestTimeoutError, StatusError

from app.llm.base import LLMProvider
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
        *,
        model: str,
        base_url: str,
        probe_timeout_seconds: float,
    ) -> None:
        """Store per-session config.

        Args:
            model: Ollama model identifier (e.g. ``"qwen3:4b"``).
            base_url: Ollama daemon URL (e.g. ``"http://localhost:11434"``).
            probe_timeout_seconds: Per-request pyreqwest timeout (seconds) for
                :meth:`list_models` and :meth:`validate_config`.
        """
        self._model = model
        self._base_url = base_url
        self._probe_timeout = probe_timeout_seconds

    def get_provider_name(self) -> str:
        """Return the wire-level provider literal."""
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
        except (ConnectError, ReadError, JSONDecodeError, RequestTimeoutError, StatusError):
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

        H1: uses pyreqwest per ADR-008 (CLAUDE.md mandate). H4: the response
        body (``.json()``) is consumed inside the ``async with`` block so the
        context manager is still active when the body is parsed.
        """
        url = f"{self._base_url.rstrip('/')}/api/tags"
        # H1/H4: pyreqwest per ADR-008; response consumed inside async-with block.
        async with (
            ClientBuilder().timeout(timedelta(seconds=self._probe_timeout)).error_for_status(True).build() as client
        ):
            resp = await client.get(url).build().send()
            payload = await resp.json()
        # Ollama /api/tags shape: { "models": [ { "name": "...", "model": "...", ... }, ... ] }
        # Match on `name` AND `model` to be robust to minor shape drift (Pitfall 4).
        models_list = payload.get("models", [])
        available = {entry.get("name") for entry in models_list if entry.get("name")} | {
            entry.get("model") for entry in models_list if entry.get("model")
        }
        return sorted(available)

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
        """Construct a PydanticAI ``Agent`` against the Ollama daemon.

        Builds an ``OpenAIChatModel`` wrapped in PydanticAI's ``OllamaProvider``
        (the OpenAI-compatible Ollama surface). The ``Agent`` carries the
        provider's qwen-friendly ``ModelProfile`` — ``thinking_tags`` parses
        ``<think>`` reasoning blocks into ``ThinkingPart`` deltas natively,
        replacing the Phase 4.5 ``reasoning=True`` flag (RESEARCH OQ-04).

        Args:
            tools: PydanticAI tool callables (each takes
                ``ctx: RunContext[deps_type]`` as first parameter).
            deps_type: ``ChatDeps`` dataclass passed through ``RunContext``
                so tools receive the per-turn flight client / session id /
                user id.

        Returns:
            A PydanticAI ``Agent`` ready for ``agent.iter(...)``.
        """
        # PydanticAI's OllamaProvider passes base_url to AsyncOpenAI, which
        # appends /chat/completions directly. Ollama serves the OpenAI-compat
        # surface at /v1/chat/completions, so the base_url must include /v1.
        # self._base_url is kept without /v1 because list_models hits /api/tags.
        bare = self._base_url.rstrip("/")
        chat_base_url = bare if bare.endswith("/v1") else bare + "/v1"
        model = OpenAIChatModel(
            self._model,
            provider=_PaiOllamaProvider(base_url=chat_base_url),
        )
        return Agent(model, tools=list(tools), deps_type=deps_type)
