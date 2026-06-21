"""Anthropic provider — wraps PydanticAI's ``AnthropicModel`` + ``AnthropicProvider``.

Phase 5 / Plan 05-03 rewrite (Wave 2): the Phase 4.5 LangChain ``bind_tools`` body
retires. :meth:`build_agent` now constructs a ``pydantic_ai.Agent`` backed by
``AnthropicModel(model, provider=PaiAnthropicProvider(api_key=...))``. PydanticAI's
``AnthropicStreamedResponse`` surfaces ``BetaThinkingBlock``/``BetaThinkingDelta``
events natively for Claude's extended-thinking models, so the thinking surface
comes "for free" without any LangChain-specific reasoning flag.

Key properties (per ``04.5-CONTEXT.md`` decisions):

- **D-13** — :meth:`validate_config` performs **key-presence
  only** validation by default. It returns
  :attr:`~app.llm.errors.ProbeErrorCode.MISSING_API_KEY` when ``self._api_key``
  is ``None`` or an empty string. It makes **no outbound HTTP call**.
- **D-04** — :meth:`list_models` returns a **curated** static
  list. Cloud providers do not perform live discovery in 4.5; the three model
  identifiers below mirror ``Settings.get_available_providers()["anthropic"]
  ["models"]``.
- **D-08** — The ``api_key`` constructor argument represents the per-session
  effective key after the factory resolves the payload-vs-env fallback
  (payload wins). The factory in :mod:`app.llm.factory` is responsible for
  that precedence; this class is a pure consumer.
- **D-09** — ``self._api_key`` is a private attribute, never logged, never
  persisted. It dies with the per-session ``LLMProvider`` instance.

**Pitfall 4 (RESEARCH.md) — ``AnthropicProvider(api_key=None)`` raises
``pydantic_ai.UserError``.** Same shape as the Phase 4.5 Pitfall 2 with
``ChatAnthropic`` — only the SDK changed. To avoid the failure mode:

1. :meth:`validate_config` MUST run before :meth:`build_agent` — and it does, by
   construction: the factory + ``ChatService.create_session`` ordering
   guarantees the sequence ``factory.build → validate_config → build_agent``.
2. As a defense-in-depth precondition guard, :meth:`build_agent` itself
   raises :class:`ValueError` when ``self._api_key is None`` BEFORE
   constructing ``AnthropicProvider``. This explicit guard survives Python -O
   mode (C5 — ``assert`` would be stripped) and converts a misuse (a direct
   caller who skips :meth:`validate_config`) into a clean
   :class:`ValueError` instead of a PydanticAI ``UserError`` whose message
   could leak field-path detail into logs.
"""

from collections.abc import Sequence
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider as _PaiAnthropicProvider

from app.llm.base import LLMProvider
from app.llm.errors import ProbeError, ProbeErrorCode

# D-04: cloud providers keep curated model lists. These three identifiers MUST
# stay in sync with ``Settings.get_available_providers()["anthropic"]["models"]``.
_CURATED_ANTHROPIC_MODELS: list[str] = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider — Phase 5 D-03 ABC subclass.

    Explicitly subclasses :class:`app.llm.base.LLMProvider` (the ABC). The
    class never imports :mod:`app.config` and never reads ``os.environ``;
    the per-session ``api_key`` is supplied by :class:`app.llm.factory.LLMProviderFactory`
    after applying D-08 precedence (payload wins over ``Settings.anthropic_api_key``).
    """

    def __init__(self, *, model: str, api_key: str | None) -> None:
        """Store per-session config; perform NO validation here.

        Args:
            model: Anthropic model identifier (e.g.
                ``"claude-3-5-sonnet-20241022"``).
            api_key: Resolved API key — ``None`` is permitted at construction
                time so :meth:`validate_config` can return a structured
                ``MISSING_API_KEY`` error rather than a PydanticAI
                ``UserError`` from inside :meth:`build_agent` (Pitfall 4).
        """
        self._model = model
        self._api_key = api_key

    def get_provider_name(self) -> str:
        """Wire-level provider name — matches ``SessionLLMConfig.provider``."""
        return "anthropic"

    async def validate_config(self) -> ProbeError | None:
        """Key-presence-only probe (D-13). Makes NO outbound HTTP call.

        Returns :class:`~app.llm.errors.ProbeError` with
        :attr:`~app.llm.errors.ProbeErrorCode.MISSING_API_KEY` when ``self._api_key``
        is ``None`` or empty (treated identically per D-08 — the truthy guard).
        Returns ``None`` on success. The hint mentions both the env-var and the
        ``/settings/providers`` UI affordance.
        """
        if not self._api_key:
            return ProbeError(
                error=ProbeErrorCode.MISSING_API_KEY,
                message="Anthropic needs an API key.",
                hint="Set ANTHROPIC_API_KEY on the backend, or paste a key in /settings/providers.",
            )
        return None

    async def list_models(self) -> list[str]:
        """Return the curated Anthropic model list (D-04).

        Cloud providers do not perform live discovery in 4.5; this list mirrors
        ``Settings.get_available_providers()["anthropic"]["models"]`` and must be
        kept in sync when models are added or retired.
        """
        return list(_CURATED_ANTHROPIC_MODELS)

    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
        """Construct a PydanticAI ``Agent`` against ``api.anthropic.com``.

        **Precondition (Pitfall 4):** ``self._api_key`` MUST be non-``None``.
        :meth:`validate_config` enforces this for the normal flow; the
        explicit ``if self._api_key is None: raise ValueError`` below is a
        defense-in-depth guard for direct callers that skip the probe —
        converting a misuse into a clean :class:`ValueError` instead of a
        ``pydantic_ai.UserError`` from inside the SDK (which can include
        field-path detail in its message). Survives Python -O mode (C5).

        Args:
            tools: PydanticAI tool callables (each takes
                ``ctx: RunContext[deps_type]`` as first parameter).
            deps_type: ``ChatDeps`` dataclass passed through ``RunContext``.

        Returns:
            A PydanticAI ``Agent`` ready for ``agent.iter(...)``.
        """
        # C5: explicit guard replaces assert (which Python -O strips). validate_config
        # gates this in the normal flow; the guard here protects direct callers
        # that skip the probe from receiving an opaque pydantic_ai.UserError.
        if self._api_key is None:
            raise ValueError(
                f"{self.get_provider_name()!r} build_agent() called with api_key=None; "
                "validate_config() must return None before build_agent() is called."
            )
        model = AnthropicModel(
            self._model,
            provider=_PaiAnthropicProvider(api_key=self._api_key),
        )
        return Agent(model, tools=list(tools), deps_type=deps_type)
