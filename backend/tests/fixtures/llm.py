"""Deterministic LLM mock for ChatService tests.

Phase 5 / Plan 05-04 (Wave 3): the LangChain-backed ``MockLLM(BaseChatModel)``
substrate retired here in favour of PydanticAI's
:class:`pydantic_ai.models.function.FunctionModel`. The public surface — the
``Content``/``Thinking``/``ToolCall`` chunk dataclasses, the three
``MockLLMStream`` classmethods (``greeting``/``single_tool_call``/
``multi_turn``), and ``make_chat_service_with_mock_llm(streams) -> ChatService``
— is preserved per CONTEXT.md D-17 + D-18.

Internals:
- ``_MockLLMProvider(LLMProvider)`` — explicit subclass of the Phase 5 ABC
  (D-03). Its ``build_agent`` returns a real :class:`pydantic_ai.Agent`
  backed by ``FunctionModel(stream_function=_make_stream_function(streams))``.
- ``_make_stream_function(streams)`` consumes one inner ``list[Chunk]`` per
  stream invocation (RESEARCH Pitfall 7: ``single_tool_call`` therefore
  returns TWO inner lists — one for the tool-call decision, one for the
  post-tool summary).
- ``streams`` may be either ``list[list[Chunk]]`` (the canonical scenario
  shape) OR a zero-arg callable raising an exception, in which case the
  stream_function re-raises on first invocation. The latter is the contract
  for ``test_chat_stream_emits_error_event_on_exception`` (CONTEXT.md
  preserved invariant: ``ErrorEvent.raw_detail = _scrub(str(exc))``).

Usage:
    from tests.fixtures.llm import (
        MockLLMStream,
        Content,
        Thinking,
        ToolCall,
        make_chat_service_with_mock_llm,
    )

    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="t")
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from pydantic_ai import Agent
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaThinkingPart,
    DeltaToolCall,
    FunctionModel,
)

from app.chat import ChatService
from app.chat.store import InMemoryConversationStore
from app.llm.base import LLMProvider
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.tools.flight_client import MockFlightAPIClient

if TYPE_CHECKING:
    # ModelMessage is annotation-only on stream_function signatures; ProbeError
    # is annotation-only on validate_config's return type. Both flagged TC0xx
    # because runtime imports were unused beyond annotations.
    from pydantic_ai.messages import ModelMessage

    from app.llm.errors import ProbeError


@dataclass(frozen=True, slots=True)
class Content:
    """A plain text content chunk emitted by the mock LLM."""

    text: str


@dataclass(frozen=True, slots=True)
class Thinking:
    """A reasoning/thinking chunk emitted by the mock LLM."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool-call chunk emitted by the mock LLM."""

    name: str
    args: dict[str, Any]
    id: str = "call_test"


Chunk = Content | Thinking | ToolCall


class MockLLMStream:
    """Pre-baked stream sequences for the three locked test scenarios.

    Each classmethod returns ``list[list[Chunk]]`` — one inner list per
    ``stream_function`` invocation (RESEARCH Pitfall 7: a tool-calling turn
    invokes the stream once per LLM hop, so ``single_tool_call`` returns TWO
    inner lists — the tool-call decision then the post-tool summary).
    """

    @classmethod
    def greeting(cls) -> list[list[Chunk]]:
        """Content-only response. One stream_function() call."""
        return [[Content("Hello! "), Content("How can I help you plan your trip today?")]]

    @classmethod
    def single_tool_call(
        cls,
        tool: str = "search_flights",
        args: dict[str, Any] | None = None,
        summary: str = "I found 5 flights from LAX to JFK.",
    ) -> list[list[Chunk]]:
        """Tool call → summary. TWO stream_function() calls (Pitfall 7)."""
        default_args: dict[str, Any] = {
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2030-06-15",
            "passengers": 1,
        }
        return [
            [ToolCall(name=tool, args=args if args is not None else default_args, id="call_test")],
            [Content(summary)],
        ]

    @classmethod
    def multi_turn(cls) -> list[list[Chunk]]:
        """References prior turn. One stream_function() call."""
        return [[Content("Based on your earlier query, "), Content("here are more options.")]]

    @classmethod
    def from_chunks(cls, chunks: list[list[Chunk]]) -> list[list[Chunk]]:
        """Pass-through for one-off custom scenarios."""
        return chunks


# Type alias for the streams argument: either pre-baked chunk lists OR a
# zero-arg callable that raises on invocation (the error-injection contract).
StreamsArg = list[list[Chunk]] | Callable[[], None]


def _make_stream_function(
    streams: StreamsArg,
) -> Callable[[list[ModelMessage], AgentInfo], AsyncIterator[Any]]:
    """Build a PydanticAI ``stream_function`` closure over ``streams``.

    Returns an ``async def stream_function(messages, agent_info)`` that
    PydanticAI's :class:`FunctionModel` invokes once per LLM hop. The
    closure pops one inner ``list[Chunk]`` per call and yields the
    corresponding PydanticAI delta types:

    - :class:`Content` → ``str`` (text delta)
    - :class:`Thinking` → ``{0: DeltaThinkingPart(content=text)}``
    - :class:`ToolCall` → ``{0: DeltaToolCall(name, json_args, tool_call_id)}``

    When ``streams`` is a zero-arg callable, the function re-raises whatever
    exception that callable throws on first invocation — used by the
    ``test_chat_stream_emits_error_event_on_exception`` Wave 0 test to
    verify the ``ErrorEvent.raw_detail = _scrub(str(exc))`` invariant.
    """
    if callable(streams):
        # Error-injection path: invoke the callable so it raises with the
        # expected exception text the ChatService should _scrub() into the
        # ErrorEvent.raw_detail.
        async def stream_function_err(messages: list[ModelMessage], agent_info: AgentInfo) -> AsyncIterator[Any]:
            streams()  # type: ignore[operator]  # raises
            # Unreachable; the yield satisfies the AsyncIterator return type.
            if False:  # pragma: no cover
                yield None

        return stream_function_err

    streams_iter: Iterator[list[Chunk]] = iter(streams)

    async def stream_function(messages: list[ModelMessage], agent_info: AgentInfo) -> AsyncIterator[Any]:
        try:
            chunks = next(streams_iter)
        except StopIteration:
            raise RuntimeError(
                "MockLLMStream exhausted: more stream_function() calls were made than "
                "pre-baked stream lists. Add another inner list to the streams= argument."
            ) from None
        for chunk in chunks:
            match chunk:
                case Content(text=t):
                    yield t
                case Thinking(text=t):
                    yield {0: DeltaThinkingPart(content=t)}
                case ToolCall(name=n, args=a, id=i):
                    yield {0: DeltaToolCall(name=n, json_args=json.dumps(a), tool_call_id=i)}

    return stream_function


class _MockLLMProvider(LLMProvider):
    """:class:`LLMProvider` ABC subclass driving a ``FunctionModel``-backed Agent.

    Per CONTEXT.md D-03 the provider explicitly subclasses the ABC. The
    interesting method is :meth:`build_agent`, which returns a real
    :class:`pydantic_ai.Agent` so tests exercise the production agent code
    path (CONTEXT.md anti-pattern: "Don't mock at the Agent level when you
    could mock at the Model level").
    """

    def __init__(self, streams: StreamsArg) -> None:
        self._streams = streams

    def get_provider_name(self) -> str:
        return "ollama"  # Wire-level name; tests don't care about the value.

    async def validate_config(self) -> ProbeError | None:
        return None

    async def list_models(self) -> list[str]:
        return []

    def build_agent(self, tools: Any, deps_type: type[Any]) -> Agent[Any, str]:
        model = FunctionModel(stream_function=_make_stream_function(self._streams))
        return Agent(model, tools=list(tools), deps_type=deps_type)


def default_session_config(provider: str = "ollama", model: str = "qwen3:4b") -> SessionLLMConfig:
    """Return a SessionLLMConfig wired with the 4.2 default fallbacks."""
    return SessionLLMConfig(provider=provider, model=model, base_url=None, api_key=None)


def make_chat_service_with_mock_llm(streams: StreamsArg) -> ChatService:
    """Build a ChatService whose factory yields a ``FunctionModel``-backed provider.

    Phase 5 / Plan 05-04: signature preserved per D-18 (existing call sites
    pass ``list[list[Chunk]]`` from the ``MockLLMStream`` classmethods).
    Internals now construct an :class:`InMemoryConversationStore` and thread
    it through ``ChatService(conversation_store=...)`` per D-08.

    The ``streams`` argument additionally accepts a zero-arg callable for
    error-injection tests (Wave 0 ``test_stream_error_event.py`` contract);
    the type alias is reflected in :data:`StreamsArg`.
    """
    flight_client = MockFlightAPIClient(seed=42)
    provider = _MockLLMProvider(streams)
    factory = MagicMock(spec=LLMProviderFactory)
    factory.build = MagicMock(return_value=provider)
    return ChatService(
        flight_client=flight_client,
        factory=factory,
        conversation_store=InMemoryConversationStore(),
    )
