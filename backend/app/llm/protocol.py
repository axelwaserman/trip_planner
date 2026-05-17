"""LLM provider Protocol — duck-typed interface for cloud + local backends.

Two ``@runtime_checkable`` Protocols govern the per-session LLM lifecycle:

- :class:`LLMProvider` is the **raw** provider returned by
  :class:`app.llm.factory.LLMProviderFactory.build`. Holds connection details,
  exposes ``validate_config`` for the session-create probe, and constructs a
  bound runnable via ``bind_tools``.
- :class:`BoundProvider` is what ``bind_tools`` returns — the tool-bound runnable
  that ``ChatService.chat_stream`` consumes via ``ainvoke`` / ``astream``. It
  exposes only those two members; calling ``bind_tools`` on a ``BoundProvider``
  is structurally impossible.

Why two Protocols (RESEARCH.md §"Pitfall 1: bind_tools Returns a Runnable, Not a
BaseChatModel"): ``BaseChatModel.bind_tools(...)`` returns
``Runnable[LanguageModelInput, AIMessage]``, NOT another ``BaseChatModel``.
A single Protocol that both has ``bind_tools`` AND exposes the bound surface
would be a lie about the LangChain shape. Verified against installed
``langchain-core`` 1.x by Pydantic field inspection.

Why Protocol, not ABC (``~/.claude/rules/python/patterns.md``): Protocols enable
duck typing without forcing implementers to inherit. The concrete provider
classes in ``app.llm.providers.*`` (Wave 2) do NOT subclass these Protocols —
they only need to match structurally. ``@runtime_checkable`` means
``isinstance(provider, LLMProvider)`` works for the Wave-0 conformance test.

Phase 6 forward-compat note (RESEARCH.md §"Phase 6 Forward-Compat Note"): when
LangChain is replaced by PydanticAI, ``bind_tools`` retires from
:class:`LLMProvider` (PydanticAI's ``Agent`` wires tools at construction time).
The Protocol surface is intentionally narrow so the rework cost is small —
``get_provider_name``, ``validate_config``, and ``list_models`` survive the
migration unchanged; only ``bind_tools`` is LangChain-specific.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.tools import BaseTool

from app.llm.errors import ProbeError


@runtime_checkable
class BoundProvider(Protocol):
    """A provider with tools already bound — what :meth:`LLMProvider.bind_tools` returns.

    The two members below match LangChain ``Runnable[LanguageModelInput, AIMessage]``
    exactly (verified against installed ``langchain-core`` 1.x). ``astream`` is
    a sync-returning method that hands back an ``AsyncIterator``; this matches
    LangChain's ``BaseChatModel.astream`` shape — do NOT mark it ``async def``.

    Consumed by :meth:`app.chat.ChatService.chat_stream`. The bound runnable
    must NOT expose ``bind_tools`` again — re-binding tools per chunk would
    silently drop session state.
    """

    async def ainvoke(self, input: list[BaseMessage], **kwargs: Any) -> AIMessage: ...

    def astream(
        self, input: list[BaseMessage], **kwargs: Any
    ) -> AsyncIterator[AIMessageChunk]: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Per-session provider built by :class:`app.llm.factory.LLMProviderFactory`.

    The four members below are the full LLM-provider contract for Phase 4.5:

    - ``get_provider_name`` returns the wire-level provider name
      (``"ollama"`` / ``"openai"`` / ``"anthropic"`` / etc.).
    - ``validate_config`` is the session-create probe — returns ``None`` on
      success, otherwise a structured :class:`app.llm.errors.ProbeError` mapping
      to UI-SPEC F1-F5.
    - ``bind_tools`` constructs the underlying chat model (e.g. ``ChatOllama``,
      ``ChatOpenAI``) with the desired tools attached and returns the bound
      runnable typed as :class:`BoundProvider`.
    - ``list_models`` returns the provider's discovered model identifiers; for
      cloud providers this is a curated allow-list, for local providers it
      hits the daemon (Ollama ``/api/tags``, LM Studio ``/v1/models``).

    Per D-07: ``list_models`` is a member of :class:`LLMProvider` (NOT
    :class:`BoundProvider`, NOT a separate probe service). Discovery is
    per-provider behaviour, so it lives on the per-provider object.
    """

    def get_provider_name(self) -> str: ...

    async def validate_config(self) -> ProbeError | None: ...

    def bind_tools(self, tools: Sequence[BaseTool]) -> BoundProvider: ...

    async def list_models(self) -> list[str]: ...
