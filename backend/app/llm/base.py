"""Phase 5 LLM provider ABC — single-tier abstract surface (D-01..D-03).

Replaces the Phase 4.5 two-tier ``LLMProvider`` Protocol pair (raw provider +
its tool-bound runnable) with a single ``LLMProvider(ABC)`` (D-01). Concrete
providers in ``app.llm.providers.*`` explicitly subclass this class — no duck
typing — per CLAUDE.md "Abstract interfaces use ``ABC``, never ``Protocol``"
(D-03).

The second tier retires entirely: PydanticAI's ``Agent`` IS the tool-bound
thing returned by :meth:`build_agent`, so a separate "already-bound" surface is
structurally redundant (CONTEXT.md anti-pattern lock: "Don't ship a
``ProtocolProvider`` adapter alongside the new ABC").

The Phase 4.5 ``bind_tools(tools)`` method is replaced by
``build_agent(tools, deps_type) -> pydantic_ai.Agent[Any, str]`` (D-02).
PydanticAI wires tools at ``Agent`` construction time, so the per-turn
re-binding loop inside ``ChatService.chat_stream`` collapses to a single
``agent.iter()`` call.

Phase forward-compat note: the four abstract methods are exactly the surface that
survives Phase 6 (PostgresConversationStore swap + cloud provider wiring).
``get_provider_name``/``validate_config``/``list_models`` carry through unchanged;
``build_agent`` returns a PydanticAI ``Agent`` that is dependency-injected via
``RunContext[ChatDeps]`` — so per-provider plumbing reduces to ``Agent``
construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    # pydantic_ai is added in Wave 4; using TYPE_CHECKING keeps this module
    # importable while Wave 1+2 land. The forward-ref string ``Agent[Any, str]``
    # in ``build_agent``'s signature is resolved by mypy/pyright but never
    # executed at runtime.
    from pydantic_ai import Agent

    from app.llm.errors import ProbeError


class LLMProvider(ABC):
    """Abstract per-session LLM provider (Phase 5 D-01..D-03).

    Concrete providers in ``app.llm.providers.*`` (Ollama, OpenAI, Anthropic,
    LM Studio) explicitly subclass this ABC. The four abstract methods below
    define the full LLM-provider contract:

    - :meth:`get_provider_name` — wire-level provider name
      (``"ollama"`` / ``"openai"`` / ``"anthropic"`` / ``"lmstudio"``).
    - :meth:`validate_config` — session-create probe; ``None`` on success,
      otherwise a structured :class:`app.llm.errors.ProbeError` mapping to
      UI-SPEC F1-F5.
    - :meth:`list_models` — provider model discovery (Ollama ``/api/tags``,
      LM Studio ``/v1/models``, curated allow-list for cloud providers).
    - :meth:`build_agent` — construct a ``pydantic_ai.Agent`` with the supplied
      tools attached and ``deps_type`` set so ``ChatService.chat_stream`` can
      thread :class:`app.chat.deps.ChatDeps` through ``RunContext``.

    Per D-03 / CLAUDE.md, this is an ``abc.ABC``, NOT a ``typing.Protocol`` —
    structural subtyping is reserved for third-party duck-typing compatibility
    only. Providers that fail to implement all four methods will fail with
    ``TypeError: Can't instantiate abstract class …`` at construction time
    (the canonical ABC enforcement, replacing the Phase 4.5 ``@runtime_checkable``
    Protocol's late-binding behaviour).
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the wire-level provider name (e.g. ``"ollama"``).

        Returns:
            The lowercase provider identifier. Stable across calls; used for
            log scrubbing, UI surfaces, and metadata indexing.
        """
        ...

    @abstractmethod
    async def validate_config(self) -> ProbeError | None:
        """Probe the provider for reachability and model presence.

        Returns:
            ``None`` if the configured ``model`` is reachable and usable, or a
            :class:`app.llm.errors.ProbeError` describing the failure (mapped
            to UI-SPEC F1-F5 by the session-create route).

        Raises:
            Never — all exceptions are converted into structured ``ProbeError``
            instances so the route layer can render them deterministically.
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Discover available models for this provider.

        For local providers (Ollama, LM Studio) this hits the daemon
        (``/api/tags``, ``/v1/models``). For cloud providers it returns a
        curated allow-list owned by ``app.config.Settings.get_available_providers``.

        Returns:
            Sorted list of model identifiers; empty list when the daemon is
            unreachable (callers map empty → "no models discovered").
        """
        ...

    @abstractmethod
    def build_agent(self, tools: Sequence[Any], deps_type: type[Any]) -> Agent[Any, str]:
        """Construct a PydanticAI ``Agent`` bound to ``tools`` and ``deps_type``.

        Replaces the Phase 4.5 ``bind_tools`` method (D-02). The returned
        ``Agent`` IS the tool-bound thing that ``ChatService.chat_stream``
        consumes via ``agent.iter(...)`` — there is no second-tier wrapper.

        Args:
            tools: Concrete PydanticAI tool functions (decorated with
                ``Agent.tool`` or registered via ``Agent(tools=...)``);
                the first parameter of each is ``ctx: RunContext[deps_type]``.
            deps_type: The dataclass type passed to ``RunContext``; for chat
                sessions this is :class:`app.chat.deps.ChatDeps`.

        Returns:
            A ``pydantic_ai.Agent`` configured with the provider's underlying
            model, the supplied tools, and the ``deps_type`` plumbed for
            per-turn dependency injection.
        """
        ...
