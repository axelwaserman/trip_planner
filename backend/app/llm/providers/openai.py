"""OpenAI provider — wraps PydanticAI's ``OpenAIChatModel`` / ``OpenAIResponsesModel``.

Phase 5 / Plan 05-03 rewrite (Wave 2): the Phase 4.5 LangChain ``bind_tools`` body
retires. :meth:`build_agent` now constructs a ``pydantic_ai.Agent`` backed by
either ``OpenAIChatModel`` (chat completions) or ``OpenAIResponsesModel`` (the
o-series responses API) — the dispatch is governed by the per-session
``o_series_prefixes`` tuple (D-14), threaded from
``Settings.openai_o_series_model_prefixes`` by the factory.

Design notes:

- **D-13 — key presence only by default.** :meth:`validate_config` performs a
  purely local truthy check on ``self._api_key``; it never makes an outbound
  HTTP call. Rationale: a freshly pasted key on ``/settings/providers`` should
  NOT trigger an OpenAI billing event on every session create.
- **D-04 — curated cloud model list.** :meth:`list_models` returns a hardcoded
  five-element allow-list matching ``Settings.get_available_providers()``.
  Cloud providers do not perform live ``/v1/models`` discovery in Phase 4.5.
- **D-08 / D-09 — key precedence + non-logging.** The API key arrives via
  ``__init__`` from the factory (which applies the precedence rule:
  payload key > ``Settings.openai_api_key`` env-var fallback). This module
  never reads from ``os.environ`` directly and never logs ``self._api_key``.
- **D-14 — o-series dispatch.** When the configured model name starts with
  one of the prefixes in ``o_series_prefixes`` (``"o1"`` / ``"o3"`` by default),
  :meth:`build_agent` constructs an ``OpenAIResponsesModel`` (PydanticAI's
  responses-API wrapper that surfaces o-series reasoning blocks). Other
  models route to ``OpenAIChatModel``. The prefix tuple lives on ``Settings``
  per CLAUDE.md "tunable thresholds live on Settings".
- **PydanticAI takes plain ``str``.** The Phase 4.5 ``SecretStr`` wrapping
  retires — PydanticAI's ``OpenAIProvider`` accepts a plain ``str`` for
  ``api_key`` (RESEARCH § "Auth shape: Plain str").
- **Defense-in-depth assert.** :meth:`build_agent` asserts
  ``self._api_key is not None`` before constructing the PydanticAI provider.
  In the normal flow :meth:`validate_config` already gates this; the assert
  protects direct callers that skip the probe.
"""

from collections.abc import Sequence
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider as _PaiOpenAIProvider

from app.llm.base import LLMProvider
from app.llm.errors import ProbeError, ProbeErrorCode


class OpenAIProvider(LLMProvider):
    """Cloud LLM provider backed by PydanticAI's OpenAI surface.

    Phase 5 D-03: explicitly subclasses :class:`app.llm.base.LLMProvider`
    (the ABC). Constructed by :class:`app.llm.factory.LLMProviderFactory`;
    the factory injects the resolved API key (payload > env-var fallback) and
    the live ``Settings.openai_o_series_model_prefixes`` value, so this class
    never reads ``os.environ`` itself.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        o_series_prefixes: tuple[str, ...] = ("o1", "o3"),
    ) -> None:
        """Store per-session config.

        Args:
            model: OpenAI model identifier (e.g. ``"gpt-4o-mini"``,
                ``"o3-mini"``).
            api_key: Resolved API key — ``None`` is permitted at construction
                time so :meth:`validate_config` can return a structured
                ``MISSING_API_KEY`` error rather than a SDK construction
                failure.
            o_series_prefixes: Model-name prefixes that route to
                ``OpenAIResponsesModel`` instead of ``OpenAIChatModel``
                (D-14). Default mirrors
                ``Settings.openai_o_series_model_prefixes``; the factory
                passes the live Settings value at construction time.
        """
        self._model = model
        self._api_key = api_key
        self._o_series_prefixes = o_series_prefixes

    def get_provider_name(self) -> str:
        """Return the wire-level provider literal."""
        return "openai"

    async def validate_config(self) -> ProbeError | None:
        """Verify the API key is present (D-13: presence only, no HTTP).

        Returns:
            ``None`` when ``self._api_key`` is a truthy non-empty string.
            :class:`ProbeError` with ``error=MISSING_API_KEY`` when the key is
            ``None`` OR an empty/whitespace string. The truthy check covers
            both cases for ``str | None``; the
            :class:`app.models.SessionCreateRequest` validator already strips
            and normalises payload keys, but defense-in-depth here guards
            against an empty literal in a misconfigured ``.env`` file.
        """
        if not self._api_key:
            return ProbeError(
                error=ProbeErrorCode.MISSING_API_KEY,
                message="OpenAI needs an API key.",
                hint="Set OPENAI_API_KEY on the backend, or paste a key in /settings/providers.",
            )
        return None

    async def list_models(self) -> list[str]:
        """Return the curated cloud allow-list (D-04 — no live discovery).

        Mirrors ``Settings.get_available_providers()["openai"]["models"]`` so
        the ``/api/llm/providers`` route and this provider class agree on the
        offered model set. Updates land in both places together when OpenAI
        publishes a new model id.
        """
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini", "o3-mini"]

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
        """Construct a PydanticAI ``Agent`` against ``api.openai.com``.

        Dispatches on the model-name prefix (D-14):

        - models matching ``self._o_series_prefixes`` (``"o1"``, ``"o3"`` by
          default) → ``OpenAIResponsesModel`` (the responses-API wrapper that
          surfaces o-series reasoning blocks).
        - everything else → ``OpenAIChatModel`` (chat completions API).

        Precondition: :meth:`validate_config` has already returned ``None``.
        The ``assert self._api_key is not None`` is defense-in-depth — for
        direct callers that skip the probe, the assert produces a clean
        ``AssertionError`` rather than a ``UserError`` from inside the SDK.

        Args:
            tools: PydanticAI tool callables (each takes
                ``ctx: RunContext[deps_type]`` as first parameter).
            deps_type: ``ChatDeps`` dataclass passed through ``RunContext``.

        Returns:
            A PydanticAI ``Agent`` ready for ``agent.iter(...)``.
        """
        assert self._api_key is not None  # validate_config gated this in normal flow
        provider = _PaiOpenAIProvider(api_key=self._api_key)
        model: OpenAIResponsesModel | OpenAIChatModel
        if any(self._model.startswith(prefix) for prefix in self._o_series_prefixes):
            model = OpenAIResponsesModel(self._model, provider=provider)
        else:
            model = OpenAIChatModel(self._model, provider=provider)
        return Agent(model, tools=list(tools), deps_type=deps_type)
