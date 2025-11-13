"""Integration tests for ChatService with mocked LLM responses.

These tests verify tool execution logic without waiting for real LLM calls.
Compatible with LangChain 1.0 patterns.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat import ChatService
from app.services.flight import FlightService
from tests.fixtures.mock_llm import (
    MockChatModel,
    create_mock_tool_result,
    mock_llm_stream_after_tool_execution,
    mock_llm_stream_no_tools,
    mock_llm_stream_with_tool_call,
)

# Mark all tests as integration tests
pytestmark = [pytest.mark.integration]


@pytest.fixture
def mock_flight_service() -> FlightService:
    """Create a real FlightService with mocked client."""
    from app.infrastructure.clients.mock import MockFlightAPIClient

    client = MockFlightAPIClient()
    return FlightService(client=client)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_emits_tool_call_event(mock_flight_service: FlightService) -> None:
    """Test that chat_stream emits tool_call event when LLM requests tool."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        # Create mock LLM that will call search_flights tool
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Stream chat and collect events
        events = []
        async for event in chat_service.chat_stream("Find flights from LAX to JFK"):
            events.append((event.event_type, event.metadata))

        # Verify tool_call event was emitted
        tool_call_events = [e for e in events if e[0] == "tool_call"]
        assert len(tool_call_events) > 0, "Expected at least one tool_call event"

        # Verify tool_call metadata
        tool_call_metadata = tool_call_events[0][1]
        assert tool_call_metadata is not None
        assert tool_call_metadata["tool_name"] == "search_flights"
        assert "arguments" in tool_call_metadata
        assert tool_call_metadata["status"] == "running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_emits_tool_result_event(mock_flight_service: FlightService) -> None:
    """Test that chat_stream emits tool_result event after tool execution."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        # Mock LLM that calls tool
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Stream chat and collect events
        events = []
        async for event in chat_service.chat_stream("Find flights from LAX to JFK"):
            events.append((event.event_type, event.metadata))

        # Verify tool_result event was emitted
        tool_result_events = [e for e in events if e[0] == "tool_result"]
        assert len(tool_result_events) > 0, "Expected at least one tool_result event"

        # Verify tool_result metadata
        result_metadata = tool_result_events[0][1]
        assert result_metadata is not None
        assert "summary" in result_metadata
        assert "full_result" in result_metadata
        assert result_metadata["status"] == "success"
        assert "elapsed_ms" in result_metadata


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_executes_tool_with_correct_arguments(
    mock_flight_service: FlightService,
) -> None:
    """Test that tool is executed with arguments from LLM."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Collect tool call arguments
        tool_args = None
        async for event in chat_service.chat_stream("Find flights from LAX to JFK"):
            if event.event_type == "tool_call" and event.metadata:
                tool_args = event.metadata["arguments"]

        # Verify tool was called with correct arguments
        assert tool_args is not None
        assert tool_args["origin"] == "LAX"
        assert tool_args["destination"] == "JFK"
        assert tool_args["departure_date"] == "2025-06-15"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_no_tool_events_for_general_conversation(
    mock_flight_service: FlightService,
) -> None:
    """Test that no tool events are emitted for general conversation."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        # Mock LLM that doesn't call tools
        mock_llm = MockChatModel(mock_llm_stream_no_tools())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Stream chat and collect events
        events = []
        async for event in chat_service.chat_stream("Hello, how are you?"):
            events.append((event.event_type, event.metadata))

        # Verify no tool events
        tool_call_events = [e for e in events if e[0] == "tool_call"]
        tool_result_events = [e for e in events if e[0] == "tool_result"]
        assert len(tool_call_events) == 0, "Expected no tool_call events"
        assert len(tool_result_events) == 0, "Expected no tool_result events"

        # Should only have content events
        content_events = [e for e in events if e[0] == "content"]
        assert len(content_events) > 0, "Expected content events"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_includes_summary_in_tool_result(
    mock_flight_service: FlightService,
) -> None:
    """Test that tool_result includes a summary (first 2-3 lines)."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Get tool result
        result_metadata = None
        async for event in chat_service.chat_stream("Find flights from LAX to JFK"):
            if event.event_type == "tool_result" and event.metadata:
                result_metadata = event.metadata
                break

        assert result_metadata is not None
        assert "summary" in result_metadata
        assert "full_result" in result_metadata

        # Summary should be a string
        assert isinstance(result_metadata["summary"], str)
        assert len(result_metadata["summary"]) > 0
        # Full result should also be a string
        assert isinstance(result_metadata["full_result"], str)
        assert len(result_metadata["full_result"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_measures_tool_execution_time(
    mock_flight_service: FlightService,
) -> None:
    """Test that tool execution time is measured and included in metadata."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Get tool result
        result_metadata = None
        async for event in chat_service.chat_stream("Find flights from LAX to JFK"):
            if event.event_type == "tool_result" and event.metadata:
                result_metadata = event.metadata
                break

        assert result_metadata is not None
        assert "elapsed_ms" in result_metadata
        assert isinstance(result_metadata["elapsed_ms"], int)
        assert result_metadata["elapsed_ms"] >= 0
        # Should be reasonably fast (mock client)
        assert result_metadata["elapsed_ms"] < 5000, "Mock tool should execute quickly"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_preserves_session_across_tool_calls(
    mock_flight_service: FlightService,
) -> None:
    """Test that session_id is consistent across all events."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # Collect session IDs
        session_ids = set()
        async for event in chat_service.chat_stream(
            "Find flights from LAX to JFK", session_id="test-session-123"
        ):
            session_ids.add(event.session_id)

        # All events should have the same session ID
        assert len(session_ids) == 1
        assert "test-session-123" in session_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_stream_adds_tool_messages_to_history(
    mock_flight_service: FlightService,
) -> None:
    """Test that tool calls and results are added to conversation history."""
    with patch("app.chat.ChatOllama") as mock_ollama_class:
        mock_llm = MockChatModel(mock_llm_stream_with_tool_call())
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.bind_tools.return_value = mock_llm
        mock_ollama_class.return_value = mock_ollama_instance

        chat_service = ChatService(flight_service=mock_flight_service)

        # First message with tool call
        session_id = None
        async for event in chat_service.chat_stream("Find flights from LAX to JFK"):
            session_id = event.session_id

        # Check conversation history
        history = chat_service._get_session_history(session_id)
        messages = list(history.messages)

        # Should have: user message, AI with tool calls, tool result, final AI response
        assert len(messages) >= 4, "Expected at least 4 messages in history"

        # Verify message types exist
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        message_types = [type(msg).__name__ for msg in messages]
        assert "HumanMessage" in message_types
        assert "AIMessage" in message_types
        assert "ToolMessage" in message_types
