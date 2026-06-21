"""LM Studio provider — wraps PydanticAI's ``OpenAIChatModel`` against a local LM Studio daemon.

Phase 5 / Plan 05-03 rewrite (Wave 2): the Phase 4.5 LangChain ``bind_tools`` body
retires. :meth:`build_agent` now constructs a ``pydantic_ai.Agent`` backed by
``OpenAIChatModel(model, provider=PaiOpenAIProvider(base_url=...))``. PydanticAI's
``OpenAIProvider`` auto-fills the ``"api-key-not-set"`` placeholder when
``base_url`` is set and ``OPENAI_API_KEY`` is unset (Phase 4.5 ``"lm-studio"``
sentinel retired).

Design notes:

- **D-15 — first-class provider class.** LM Studio is a peer of Ollama / OpenAI /
  Anthropic, not a hidden adapter. The factory match block dispatches
  ``"lmstudio"`` to this class.

- **D-16 — OpenAI-compatible delegation.** LM Studio exposes an OpenAI-compatible
  REST surface; the provider re-uses PydanticAI's ``OpenAIChatModel`` with a
  custom ``base_url`` pointing at the local daemon. No second SDK dependency.

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

- **ADR-008 — pyreqwest per CLAUDE.md.** ``validate_config`` and
  ``list_models`` use ``pyreqwest`` for ``/models`` probes (H1, Phase 07 fix).
  The response JSON is consumed inside the ``async with`` block (H4) to ensure
  the context manager is still active when the body is parsed.

Cross-reference: :meth:`build_agent` is structurally symmetric with
:meth:`app.llm.providers.openai.OpenAIProvider.build_agent` for the
non-o-series branch — only the ``base_url`` differs.
"""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider as _PaiOpenAIProvider
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, JSONDecodeError, ReadError, RequestTimeoutError, StatusError

from app.llm.base import LLMProvider
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

    def __init__(self, *, model: str, base_url: str, probe_timeout_seconds: float) -> None:
        """Construct with model id, daemon base URL, and probe timeout.

        Args:
            model: LM Studio model identifier (e.g. ``"qwen2.5-coder-7b"``).
                Per D-18 the value is whatever the daemon returned from a
                prior dynamic discovery call — NOT a curated allow-list.
            base_url: LM Studio daemon URL including the ``/v1`` prefix
                (e.g. ``"http://localhost:1234/v1"``). The factory injects
                either the request payload's value or
                :attr:`Settings.lmstudio_base_url`.
            probe_timeout_seconds: Per-request pyreqwest timeout (seconds) for
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
        except (ConnectError, ReadError, JSONDecodeError, RequestTimeoutError, StatusError):
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

        H1: uses pyreqwest per ADR-008 (CLAUDE.md mandate). H4: the response
        body is consumed inside the ``async with`` block so the context manager
        is still active when the body is parsed.
        """
        url = f"{self._base_url.rstrip('/')}/models"
        # H1/H4: pyreqwest per ADR-008; response consumed inside async-with block.
        async with ClientBuilder().timeout(timedelta(seconds=self._probe_timeout)).error_for_status(True).build() as client:
            resp = await client.get(url).build().send()
            payload = await resp.json()
        # LM Studio models endpoint shape: {"object": "list", "data": [{"id": "...", "object": "model", ...}]}
        # Defensive parse — Assumption A4 — empty list on shape drift.
        data = payload.get("data", [])
        if not isinstance(data, list):
            return []
        return sorted({entry["id"] for entry in data if isinstance(entry, dict) and entry.get("id")})

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
        """Construct a PydanticAI ``Agent`` against the LM Studio daemon.

        Builds an ``OpenAIChatModel`` wrapped in PydanticAI's ``OpenAIProvider``
        with the ``base_url`` pointed at the local LM Studio daemon. The
        Phase 4.5 ``SecretStr("lm-studio")`` sentinel retires — PydanticAI's
        ``OpenAIProvider`` auto-fills ``"api-key-not-set"`` when ``base_url``
        is provided and ``OPENAI_API_KEY`` is unset (RESEARCH § "LM Studio
        Provider"). Because ``base_url`` overrides the destination, the
        placeholder never reaches ``api.openai.com``.

        Args:
            tools: PydanticAI tool callables (each takes
                ``ctx: RunContext[deps_type]`` as first parameter).
            deps_type: ``ChatDeps`` dataclass passed through ``RunContext``.

        Returns:
            A PydanticAI ``Agent`` ready for ``agent.iter(...)``.
        """
        model = OpenAIChatModel(
            self._model,
            provider=_PaiOpenAIProvider(base_url=self._base_url),
        )
        return Agent(model, tools=list(tools), deps_type=deps_type)
