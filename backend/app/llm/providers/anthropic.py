"""Anthropic provider — wraps :class:`langchain_anthropic.ChatAnthropic`.

This module implements the ``LLMProvider`` Protocol (:mod:`app.llm.protocol`)
for Anthropic Claude models. It is the second REAL cloud provider in Phase 4.5
(success criterion #3 of the phase ROADMAP) and is symmetric with the OpenAI
provider, with one critical difference (Pitfall 2 below).

Key properties (per ``04.5-CONTEXT.md`` decisions):

- **D-13** — :meth:`AnthropicProvider.validate_config` performs **key-presence
  only** validation by default. It returns
  :attr:`~app.llm.errors.ProbeErrorCode.MISSING_API_KEY` when ``self._api_key``
  is ``None`` or an empty string. It makes **no outbound HTTP call** — that is
  reserved for the opt-in ``POST /api/providers/{provider}/test`` endpoint
  landing in a later plan, which emits the new
  :attr:`~app.llm.errors.ProbeErrorCode.INVALID_API_KEY` value.
- **D-04** — :meth:`AnthropicProvider.list_models` returns a **curated** static
  list. Cloud providers do not perform live discovery in 4.5; the three model
  identifiers below mirror ``Settings.get_available_providers()["anthropic"]
  ["models"]``.
- **D-08** — The ``api_key`` constructor argument represents the per-session
  effective key after the factory resolves the payload-vs-env fallback
  (payload wins). The factory in :mod:`app.llm.factory` is responsible for
  that precedence; this class is a pure consumer.
- **D-09** — ``self._api_key`` is a private attribute, never logged, never
  persisted. It dies with the per-session ``LLMProvider`` instance.

**Pitfall 2 — ChatAnthropic requires a non-``None`` ``api_key`` at construction
time.** Unlike :class:`langchain_openai.ChatOpenAI`,
:class:`langchain_anthropic.ChatAnthropic` declares ``anthropic_api_key`` as a
**required** Pydantic ``SecretStr`` (NOT ``Optional``). Constructing
``ChatAnthropic(api_key=None)`` raises a Pydantic ``ValidationError`` BEFORE any
user code can intercept it — and that error's stack trace can include the field
path, which is a (small) information-disclosure surface. To avoid this:

1. :meth:`validate_config` MUST run before :meth:`bind_tools` — and it does, by
   construction: the factory + ``ChatService.create_session`` ordering
   (Plan 06) guarantees the sequence
   ``factory.build → validate_config → bind_tools``.
2. As a defense-in-depth precondition guard, :meth:`bind_tools` itself
   ``assert``s ``self._api_key is not None`` BEFORE constructing
   ``ChatAnthropic``. That asserts converts a misuse (a direct caller who skips
   :meth:`validate_config`) into a clean :class:`AssertionError` instead of a
   Pydantic ``ValidationError`` from inside the SDK.
"""

from collections.abc import Sequence

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import BaseTool
from pydantic import SecretStr

from app.llm.errors import ProbeError, ProbeErrorCode
from app.llm.protocol import BoundProvider

# D-04: cloud providers keep curated model lists. These three identifiers MUST
# stay in sync with ``Settings.get_available_providers()["anthropic"]["models"]``.
_CURATED_ANTHROPIC_MODELS: list[str] = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


class AnthropicProvider:
    """Anthropic Claude provider — implements :class:`app.llm.protocol.LLMProvider`.

    The class never imports :mod:`app.config` and never reads ``os.environ``;
    the per-session ``api_key`` is supplied by :class:`app.llm.factory.LLMProviderFactory`
    after applying D-08 precedence (payload wins over ``Settings.anthropic_api_key``).
    """

    def __init__(self, model: str, api_key: str | None) -> None:
        """Store per-session config; perform NO validation here.

        Validation lives in :meth:`validate_config` (key-presence) and the
        :meth:`bind_tools` precondition assert (Pitfall 2 guard). The factory
        constructs us with ``api_key`` already resolved per D-08.
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
        ``/settings/providers`` UI affordance from Plan 08+.
        """
        if not self._api_key:
            return ProbeError(
                error=ProbeErrorCode.MISSING_API_KEY,
                message="Anthropic needs an API key.",
                hint="Set ANTHROPIC_API_KEY on the backend, or paste a key in /settings/providers.",
            )
        return None

    def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider:
        """Construct :class:`ChatAnthropic` with tools bound; return the runnable.

        **Precondition (Pitfall 2):** ``self._api_key`` MUST be non-``None``.
        :meth:`validate_config` enforces this for the normal flow; the bare
        ``assert`` below is a defense-in-depth guard for direct callers that
        skip the probe — converting a misuse into a clean :class:`AssertionError`
        instead of a Pydantic ``ValidationError`` from inside the SDK (which
        would include the field path in its stack trace).

        The bound runnable returned by ``ChatAnthropic.bind_tools`` is
        ``Runnable[LanguageModelInput, AIMessage]``; it structurally satisfies
        the :class:`BoundProvider` Protocol (``ainvoke`` + ``astream``) but
        mypy cannot prove this statically because ``Runnable`` is not declared
        as implementing the Protocol — hence the ``type: ignore[return-value]``.
        """
        # Pitfall 2: ChatAnthropic requires non-None api_key at construction;
        # validate_config gates this in the normal flow (factory ordering, Plan 06).
        assert self._api_key is not None  # bind_tools precondition (Pitfall 2)
        # ChatAnthropic.anthropic_api_key is a Pydantic SecretStr (alias ``api_key``);
        # wrap explicitly so the type matches the declared field. The ``call-arg``
        # ignore is needed because the Pydantic-plugin treats several aliased fields
        # (``timeout``, ``stop``) as positionally required even though they have
        # ``Field(None, alias=...)`` defaults at runtime — verified against
        # langchain_anthropic 1.4.3. ``populate_by_name=True`` is set on the model so
        # passing ``model=`` (not the ``model_name`` alias) is supported at runtime.
        llm = ChatAnthropic(  # type: ignore[call-arg]
            model=self._model,
            api_key=SecretStr(self._api_key),
        )
        # Runnable[LanguageModelInput, AIMessage] structurally satisfies BoundProvider;
        # mypy cannot prove this without importing LangChain's runtime Protocol check.
        return llm.bind_tools(list(tools))  # type: ignore[return-value]

    async def list_models(self) -> list[str]:
        """Return the curated Anthropic model list (D-04).

        Cloud providers do not perform live discovery in 4.5; this list mirrors
        ``Settings.get_available_providers()["anthropic"]["models"]`` and must be
        kept in sync when models are added or retired.
        """
        return list(_CURATED_ANTHROPIC_MODELS)
