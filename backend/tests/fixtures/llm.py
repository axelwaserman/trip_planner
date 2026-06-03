"""Deterministic LLM mock for ChatService tests.

Usage:
    from tests.fixtures.llm import (
        MockLLM,
        MockLLMStream,
        Content,
        Thinking,
        ToolCall,
        make_chat_service_with_mock_llm,
    )

    # Service-layer test (fast, no HTTP) — Phase 4.5 factory contract
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="t")

    # HTTP-layer test: replace app.state.chat_service after TestClient starts
    with TestClient(app) as client:
        client.app.state.chat_service = make_chat_service_with_mock_llm(
            MockLLMStream.single_tool_call(),
        )
"""

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from app.chat import ChatService
from app.llm.errors import ProbeError
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.tools.flight_client import MockFlightAPIClient


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


class MockLLM(BaseChatModel):
    """Deterministic LLM mock for tests. Accepts pre-baked chunk sequences.

    Each element of ``streams`` is a list of ``Chunk`` objects that will be
    yielded on one ``astream()`` call.  The tool-call → summary flow requires
    two inner lists: one with a ``ToolCall`` chunk (first ``astream()`` call)
    and one with the summary ``Content`` chunks (second ``astream()`` call).
    """

    _streams_iter: Any = PrivateAttr()

    def __init__(self, streams: list[list[Chunk]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._streams_iter = iter(streams)

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Required by BaseChatModel abstract interface; unused in streaming tests."""
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        try:
            chunks: list[Chunk] = next(self._streams_iter)
        except StopIteration:
            raise RuntimeError(
                "MockLLM exhausted: more astream() calls were made than pre-baked stream lists. "
                "Add another inner list to the streams= argument."
            ) from None
        for chunk in chunks:
            match chunk:
                case Content(text=t):
                    yield ChatGenerationChunk(message=AIMessageChunk(content=t))
                case Thinking(text=t):
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(
                            content="",
                            additional_kwargs={"reasoning_content": t},
                        )
                    )
                case ToolCall(name=n, args=a, id=i):
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(
                            content="",
                            tool_call_chunks=[ToolCallChunk(name=n, args=json.dumps(a), id=i, index=0)],
                        )
                    )

    def bind_tools(self, tools: Any, **kwargs: Any) -> "MockLLM":
        """Return self — mock controls its own output regardless of bound tools."""
        return self


class MockLLMStream:
    """Pre-baked stream sequences for the three locked test scenarios.

    Each classmethod returns ``list[list[Chunk]]`` — one inner list per
    ``astream()`` call that ``ChatService.chat_stream()`` will make.
    """

    @classmethod
    def greeting(cls) -> list[list[Chunk]]:
        """Content-only response. One astream() call."""
        return [[Content("Hello! "), Content("How can I help you plan your trip today?")]]

    @classmethod
    def single_tool_call(
        cls,
        tool: str = "search_flights",
        args: dict[str, Any] | None = None,
        summary: str = "I found 5 flights from LAX to JFK.",
    ) -> list[list[Chunk]]:
        """Tool call → summary. Two astream() calls."""
        default_args: dict[str, Any] = {
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2026-06-15",
            "passengers": 1,
        }
        return [
            [ToolCall(name=tool, args=args if args is not None else default_args, id="call_test")],
            [Content(summary)],
        ]

    @classmethod
    def multi_turn(cls) -> list[list[Chunk]]:
        """References prior turn. One astream() call."""
        return [[Content("Based on your earlier query, "), Content("here are more options.")]]

    @classmethod
    def from_chunks(cls, chunks: list[list[Chunk]]) -> list[list[Chunk]]:
        """Pass-through for one-off custom scenarios."""
        return chunks


# ---------------------------------------------------------------------------
# Phase 4.5 adapter: wrap MockLLM in an LLMProvider/BoundProvider so tests
# that pre-date the factory contract still work without bringing back the
# old ChatService(llm=) keyword.
# ---------------------------------------------------------------------------


class _MockBoundProvider:
    """BoundProvider adapter — forwards astream/ainvoke to a MockLLM instance.

    The wrapped MockLLM is a real BaseChatModel subclass, so its astream
    and ainvoke surfaces already match BoundProvider's Protocol shape.
    """

    def __init__(self, llm: MockLLM) -> None:
        self._llm = llm

    def astream(self, input: list[BaseMessage], **kwargs: Any) -> AsyncIterator[AIMessageChunk]:
        return self._llm.astream(input, **kwargs)  # type: ignore[return-value]

    async def ainvoke(self, input: list[BaseMessage], **kwargs: Any) -> AIMessage:
        return await self._llm.ainvoke(input, **kwargs)


class _MockLLMProvider:
    """LLMProvider adapter — surfaces a MockLLM through the Phase 4.5 contract."""

    def __init__(self, llm: MockLLM) -> None:
        self._llm = llm

    def get_provider_name(self) -> str:
        return "ollama"  # Wire-level name; tests don't care about the value.

    async def validate_config(self) -> ProbeError | None:
        return None

    def bind_tools(self, tools: Sequence[BaseTool]) -> Any:
        # MockLLM controls its own output regardless of bound tools (see its
        # bind_tools() — it just returns self). The bound wrapper exposes
        # only astream + ainvoke as the Phase 4.5 BoundProvider Protocol
        # requires. Phase 5 / Plan 05-04 (Wave 3) replaces this whole fixture
        # with a FunctionModel-backed PydanticAI ``Agent``; the Wave 2 sweep
        # only retypes the annotation so the module imports without the
        # legacy ``protocol`` shim.
        return _MockBoundProvider(self._llm)

    async def list_models(self) -> list[str]:
        return []


def default_session_config(provider: str = "ollama", model: str = "qwen3:4b") -> SessionLLMConfig:
    """Return a SessionLLMConfig wired with the 4.2 default fallbacks."""
    return SessionLLMConfig(provider=provider, model=model, base_url=None, api_key=None)


def make_chat_service_with_mock_llm(streams: list[list[Chunk]]) -> ChatService:
    """Build a ChatService whose factory yields a MockLLM-backed provider.

    Phase 4.5 introduced the LLMProviderFactory abstraction; tests that need
    a deterministic LLM stream now wrap the existing MockLLM in a tiny
    Protocol-conforming adapter and feed it through a MagicMock factory.
    Two upsides: (1) tests stop calling the obsolete
    ``ChatService(llm=)`` constructor, (2) the adapter exercises the same
    code path production sessions take (factory.build → validate_config →
    bind_tools).
    """
    flight_client = MockFlightAPIClient(seed=42)
    provider = _MockLLMProvider(MockLLM(streams=streams))
    factory = MagicMock(spec=LLMProviderFactory)
    factory.build = MagicMock(return_value=provider)
    return ChatService(flight_client=flight_client, factory=factory)
