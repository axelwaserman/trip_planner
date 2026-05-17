"""Deterministic LLM mock for ChatService tests.

Usage:
    from tests.fixtures.llm import MockLLM, MockLLMStream, Content, Thinking, ToolCall

    # Service-layer test (fast, no HTTP)
    mock = MockLLM(streams=MockLLMStream.greeting())
    service = ChatService(flight_client=MockFlightAPIClient(seed=42), llm=mock)

    # HTTP-layer test: replace app.state.chat_service after TestClient starts
    with TestClient(app) as client:
        client.app.state.chat_service = ChatService(
            flight_client=MockFlightAPIClient(seed=42),
            llm=MockLLM(streams=MockLLMStream.single_tool_call()),
        )
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr


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

    async def _astream(  # noqa: async generator satisfies AsyncIterator
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        chunks: list[Chunk] = next(self._streams_iter)
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
                            tool_call_chunks=[
                                ToolCallChunk(name=n, args=json.dumps(a), id=i, index=0)
                            ],
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
