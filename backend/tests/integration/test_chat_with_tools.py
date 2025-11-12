"""Integration tests for ChatService with flight search tool.

Note: These tests focus on testable aspects without requiring a real LLM
with tool-calling capabilities. Full end-to-end testing with actual tool calls
should be done with manual testing or E2E tests using a compatible model.

deepseek-r1:8b does not support tool calling, so agent integration tests
that require actual LLM tool invocation are documented but not executed.
"""

from unittest.mock import AsyncMock

import pytest

from app.chat import ChatService
from app.services.flight import FlightService


@pytest.fixture
def mock_flight_service() -> AsyncMock:
    """Create mock flight service."""
    return AsyncMock(spec=FlightService)


def test_chat_service_creates_agent_with_tools(
    mock_flight_service: AsyncMock,
) -> None:
    """Test ChatService initializes LLM with flight search tool."""
    chat_service = ChatService(flight_service=mock_flight_service)

    # LLM with tools should be created
    assert chat_service.llm is not None
    assert chat_service.search_flights_tool is not None


def test_chat_service_creates_unique_sessions(
    mock_flight_service: AsyncMock,
) -> None:
    """Test chat service can create new sessions and retrieve histories."""
    chat_service = ChatService(flight_service=mock_flight_service)

    # Get two different session histories
    session_id1 = "test-session-1"
    session_id2 = "test-session-2"

    history1 = chat_service._get_session_history(session_id1)
    history2 = chat_service._get_session_history(session_id2)

    # Should be different history objects
    assert history1 is not history2

    # Should be stored in the store
    assert session_id1 in chat_service.store
    assert session_id2 in chat_service.store


def test_chat_service_session_history_persists(
    mock_flight_service: AsyncMock,
) -> None:
    """Test session history is preserved across multiple retrievals."""
    chat_service = ChatService(flight_service=mock_flight_service)

    session_id = "test-session"

    # Get history and add a message
    history1 = chat_service._get_session_history(session_id)
    history1.add_user_message("Hello")

    # Retrieve history again
    history2 = chat_service._get_session_history(session_id)

    # Should be the same object
    assert history1 is history2
    # Should still have the message
    assert len(history2.messages) == 1
    assert history2.messages[0].content == "Hello"


def test_flight_search_tool_is_available(
    mock_flight_service: AsyncMock,
) -> None:
    """Test that flight search tool is properly registered."""
    chat_service = ChatService(flight_service=mock_flight_service)

    # Tool should be available
    assert chat_service.search_flights_tool is not None
    assert chat_service.search_flights_tool.name == "search_flights"


# ============================================================================
# E2E Test Documentation (Requires Tool-Compatible LLM)
# ============================================================================
#
# The following tests document expected behavior but cannot be executed
# with deepseek-r1:8b as it doesn't support tool calling.
#
# These should be tested manually or in E2E tests with a tool-compatible model
# such as GPT-4, Claude, or Llama with tool support.
#
# Expected Agent Behaviors:
# -------------------------
#
# 1. **Tool Invocation**
#    - Agent should call flight_search tool when asked about flights
#    - Should NOT call tool for general queries ("Hello", "How are you?")
#
# 2. **Parameter Extraction**
#    - Extract IATA codes from city names ("Los Angeles" -> "LAX")
#    - Parse dates from natural language ("June 1st, 2025" -> 2025-06-01)
#    - Handle passenger counts ("for 2 people" -> passengers=2)
#
# 3. **Missing Parameter Handling**
#    - Ask for clarification when origin/destination/date missing
#    - Example: "I want to fly to New York" -> "When would you like to travel?"
#
# 4. **Filter Application**
#    - "direct flights" -> max_stops=0
#    - "under $400" -> max_price=400.00
#    - "fastest" -> sort_by="duration"
#    - "cheapest" -> sort_by="price"
#
# 5. **Error Handling**
#    - No flights found -> Suggest alternatives or broader search
#    - Invalid IATA codes -> Ask for clarification
#    - API errors -> Inform user gracefully
#
# 6. **Multi-turn Context**
#    - Remember previous searches in conversation
#    - "What's the cheapest option?" -> Reference last search results
#    - "Show me direct flights only" -> Refine last search
#
# 7. **Result Formatting**
#    - Include flight details in natural language response
#    - Mention flight IDs for potential future booking reference
#    - Format prices, times, and durations readably
#
# Manual Test Cases:
# -----------------
#
# ```python
# # Test 1: Basic flight search
# await chat_service.chat("Find flights from LAX to JFK on June 1st, 2025")
# # Expected: Tool called with correct parameters, response includes flight options
#
# # Test 2: Natural language parameters
# await chat_service.chat("I need to fly from Los Angeles to New York tomorrow")
# # Expected: City names converted to IATA, date calculated
#
# # Test 3: Filters
# await chat_service.chat("Show me direct flights under $500")
# # Expected: max_stops=0, max_price=500.0
#
# # Test 4: Multi-turn
# _, session = await chat_service.chat("Find flights LAX to JFK on June 1st")
# await chat_service.chat("What's the earliest departure?", session_id=session)
# # Expected: Agent references previous results
#
# # Test 5: General chat
# await chat_service.chat("Hello, how are you?")
# # Expected: Response without calling flight tool
# ```
#
# ============================================================================
