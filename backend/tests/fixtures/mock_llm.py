"""Mock LLM responses for fast integration testing with LangChain 1.0.

These mocks are compatible with LangChain 1.0's AIMessage and streaming patterns.
"""

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage


class MockAIMessageChunk(AIMessage):
    """Mock AIMessage chunk compatible with LangChain 1.0 streaming."""

    def __init__(
        self,
        content: str | list[str | dict[str, Any]] = "",
        tool_calls: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """Initialize mock message chunk.

        Args:
            content: Message content (string or list for LangChain 1.0)
            tool_calls: Optional tool calls in LangChain format
            **kwargs: Additional AIMessage kwargs
        """
        super().__init__(content=content, **kwargs)
        self.tool_calls = tool_calls or []


async def mock_llm_stream_with_tool_call() -> AsyncGenerator[MockAIMessageChunk, None]:
    """Mock LLM stream that calls search_flights tool.

    Simulates LangChain 1.0 behavior:
    1. First chunk contains tool_calls (no content yet)
    2. No additional chunks until tool execution completes

    Yields:
        MockAIMessageChunk with tool call
    """
    yield MockAIMessageChunk(
        content="",
        tool_calls=[
            {
                "name": "search_flights",
                "args": {
                    "origin": "LAX",
                    "destination": "JFK",
                    "departure_date": "2025-06-15",
                    "passengers": 1,
                },
                "id": "call_test_123",
            }
        ],
    )


async def mock_llm_stream_after_tool_execution() -> AsyncGenerator[MockAIMessageChunk, None]:
    """Mock LLM stream after tool has executed.

    Simulates LangChain 1.0 behavior when LLM receives tool results
    and generates final response.

    Yields:
        Content chunks for final response
    """
    yield MockAIMessageChunk(content="I found ")
    yield MockAIMessageChunk(content="5 flights ")
    yield MockAIMessageChunk(content="from LAX to JFK. ")
    yield MockAIMessageChunk(content="The cheapest option is $280.")


async def mock_llm_stream_no_tools() -> AsyncGenerator[MockAIMessageChunk, None]:
    """Mock LLM stream for general conversation without tool calls.

    Yields:
        Content chunks for conversational response
    """
    yield MockAIMessageChunk(content="Hello! ")
    yield MockAIMessageChunk(content="I'm a travel ")
    yield MockAIMessageChunk(content="planning assistant. ")
    yield MockAIMessageChunk(content="How can I help you today?")


async def mock_llm_stream_multi_turn() -> AsyncGenerator[MockAIMessageChunk, None]:
    """Mock LLM stream for multi-turn conversation.

    Simulates remembering context from previous messages.

    Yields:
        Content chunks referencing previous context
    """
    yield MockAIMessageChunk(content="Based on ")
    yield MockAIMessageChunk(content="your previous search, ")
    yield MockAIMessageChunk(content="here are some ")
    yield MockAIMessageChunk(content="alternative options.")


def create_mock_tool_result(
    origin: str = "LAX",
    destination: str = "JFK",
    num_flights: int = 5,
) -> str:
    """Create mock tool result string matching real tool output format.

    Args:
        origin: Origin airport code
        destination: Destination airport code
        num_flights: Number of flights to include in result

    Returns:
        Formatted tool result string
    """
    return f"""Found {num_flights} flights from {origin} to {destination}:

| Flight | Airline | Departure | Arrival | Duration | Stops | Price | Class |
|--------|---------|-----------|---------|----------|-------|-------|-------|
| AA100 | American Airlines | 10:00 | 16:00 | 6h 0m | 0 | $350.00 | economy |
| DL200 | Delta Air Lines | 12:00 | 19:00 | 7h 0m | 1 | $280.00 | economy |
| UA300 | United Airlines | 14:00 | 21:30 | 7h 30m | 1 | $310.00 | economy |

Route: {origin} → {destination}
"""


# Patterns for testing LangChain 1.0 tool execution
class MockChatModel:
    """Mock ChatModel for testing ChatService without real LLM.

    Compatible with LangChain 1.0 bind_tools() pattern.
    """

    def __init__(self, stream_generator: AsyncGenerator[MockAIMessageChunk, None]):
        """Initialize with stream generator.

        Args:
            stream_generator: Async generator yielding MockAIMessageChunk instances
        """
        self.stream_generator = stream_generator
        self._tools: list[Any] = []

    def bind_tools(self, tools: list[Any]) -> "MockChatModel":
        """Mock bind_tools() method.

        Args:
            tools: List of tools to bind

        Returns:
            Self for chaining
        """
        self._tools = tools
        return self

    def astream(self, messages: list[Any]) -> AsyncGenerator[MockAIMessageChunk, None]:
        """Mock astream() method.

        Args:
            messages: Input messages (ignored in mock)

        Returns:
            Async generator of message chunks
        """
        return self.stream_generator
