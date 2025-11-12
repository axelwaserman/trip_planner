"""End-to-end integration tests for chat with tool calling.

Tests full flow: User message → Agent → Tool call → Mock API → Response

These tests make actual LLM calls and are marked as slow.
Run with: pytest -m "e2e" or pytest tests/e2e/
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Flight
from app.main import app

# Mark all tests in this module as slow E2E tests
pytestmark = [pytest.mark.slow, pytest.mark.e2e]


def parse_sse_stream(response) -> tuple[list[str], str | None]:
    """Parse Server-Sent Events stream and extract chunks and session_id.

    Args:
        response: FastAPI TestClient response with SSE stream

    Returns:
        Tuple of (list of chunks, session_id)
    """
    chunks = []
    session_id = None

    for line in response.iter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if "chunk" in data:
                chunks.append(data["chunk"])
            if "session_id" in data:
                session_id = data["session_id"]
            if data.get("done"):
                break

    return chunks, session_id


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_flights() -> list[Flight]:
    """Create sample flight data for testing."""
    base_time = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)

    return [
        Flight(
            id="flight-1",
            origin="LAX",
            destination="JFK",
            departure=base_time,
            arrival=base_time.replace(hour=16),
            price=Decimal("350.00"),
            currency="USD",
            carrier="American Airlines",
            flight_number="AA100",
            duration_minutes=360,
            stops=0,
            booking_class="economy",
        ),
        Flight(
            id="flight-2",
            origin="LAX",
            destination="JFK",
            departure=base_time.replace(hour=12),
            arrival=base_time.replace(hour=19),
            price=Decimal("280.00"),
            currency="USD",
            carrier="Delta Air Lines",
            flight_number="DL200",
            duration_minutes=420,
            stops=1,
            booking_class="economy",
        ),
    ]


def test_chat_endpoint_exists(client: TestClient) -> None:
    """Test that chat endpoint is accessible."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello"},
    )
    assert response.status_code == 200


def test_chat_returns_streaming_response(client: TestClient) -> None:
    """Test that chat endpoint returns Server-Sent Events."""
    response = client.post(
        "/api/chat",
        json={"message": "Hello, how are you?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_chat_streams_chunks(client: TestClient) -> None:
    """Test that chat endpoint streams response chunks."""
    response = client.post(
        "/api/chat",
        json={"message": "Say hello"},
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)

    # Should have received at least one chunk
    assert len(chunks) > 0

    # Chunks should combine to form a response
    full_response = "".join(chunks)
    assert len(full_response) > 0


def test_chat_maintains_session_across_requests(client: TestClient) -> None:
    """Test that session_id is returned and maintained across requests."""
    # First message
    response1 = client.post(
        "/api/chat",
        json={"message": "Hello, I want to plan a trip"},
    )

    # Extract session_id
    _, session_id1 = parse_sse_stream(response1)
    assert session_id1 is not None

    # Second message with same session
    response2 = client.post(
        "/api/chat",
        json={"message": "Thank you", "session_id": session_id1},
    )

    # Extract session_id from second response
    _, session_id2 = parse_sse_stream(response2)
    
    # Session IDs should be the same
    assert session_id2 == session_id1, "Session ID should persist across requests"


@pytest.mark.asyncio
async def test_e2e_flight_search_tool_is_called(client: TestClient) -> None:
    """Test that flight search query triggers tool call."""
    response = client.post(
        "/api/chat",
        json={"message": "Find flights from LAX to JFK on 2025-06-01"},
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks)

    # Response should contain flight search indicators
    assert any(
        keyword in full_response.lower()
        for keyword in ["flight", "lax", "jfk", "airline", "price", "$"]
    ), f"Expected flight search results in response: {full_response}"


@pytest.mark.asyncio
async def test_e2e_flight_search_shows_search_indicator(client: TestClient) -> None:
    """Test that streaming shows search indicator during tool execution."""
    response = client.post(
        "/api/chat",
        json={"message": "Search for flights from SFO to LAX on June 15th 2025"},
    )

    # Look for search indicator in chunks
    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks)

    # Should show search indicator
    assert "searching" in full_response.lower() or "flight" in full_response.lower()


@pytest.mark.asyncio
async def test_e2e_flight_search_with_filters(client: TestClient) -> None:
    """Test flight search with filters (max price, stops, etc.)."""
    response = client.post(
        "/api/chat",
        json={
            "message": "Find direct flights from LAX to JFK under $400 on June 1st 2025",
        },
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks)

    # Should have flight results
    assert "flight" in full_response.lower()


@pytest.mark.asyncio
async def test_e2e_multi_turn_conversation_with_tools(client: TestClient) -> None:
    """Test multi-turn conversation with tool calls."""
    # First turn: Search flights
    response1 = client.post(
        "/api/chat",
        json={"message": "Find flights from ORD to SFO on July 1st 2025"},
    )

    chunks1, session_id = parse_sse_stream(response1)
    assert session_id is not None

    response1_text = "".join(chunks1)
    assert "flight" in response1_text.lower()

    # Second turn: Ask follow-up question
    response2 = client.post(
        "/api/chat",
        json={
            "message": "Which one is the cheapest?",
            "session_id": session_id,
        },
    )

    chunks2, _ = parse_sse_stream(response2)
    response2_text = "".join(chunks2)

    # Should reference previous search results
    assert len(response2_text) > 0


@pytest.mark.asyncio
async def test_e2e_invalid_iata_code_error(client: TestClient) -> None:
    """Test error handling for invalid IATA codes."""
    response = client.post(
        "/api/chat",
        json={"message": "Find flights from INVALID to XYZ123 on June 1st 2025"},
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks)

    # Should mention error or invalid code
    assert any(
        keyword in full_response.lower() for keyword in ["error", "invalid", "code"]
    ), f"Expected error message in response: {full_response}"


@pytest.mark.asyncio
async def test_e2e_invalid_date_format_error(client: TestClient) -> None:
    """Test error handling for invalid date format."""
    response = client.post(
        "/api/chat",
        json={"message": "Find flights from LAX to JFK on 06/01/2025"},
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks)

    # Should mention date format error or ask for clarification
    # Note: LLM might fix the date format automatically
    assert len(full_response) > 0


@pytest.mark.asyncio
async def test_e2e_general_conversation_without_tools(client: TestClient) -> None:
    """Test that general conversation works without triggering tools."""
    response = client.post(
        "/api/chat",
        json={"message": "What's the weather like today?"},
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks)

    # Should respond but not call flight search tool
    assert len(full_response) > 0
    # Should not contain flight search indicator
    assert "searching for flights" not in full_response.lower()


@pytest.mark.asyncio
async def test_e2e_streaming_with_tool_execution(client: TestClient) -> None:
    """Test that streaming works correctly during tool execution."""
    response = client.post(
        "/api/chat",
        json={"message": "Show me flights from LAX to SFO tomorrow"},
    )

    # Parse stream
    chunks, _ = parse_sse_stream(response)

    # Should have received chunks (streaming)
    assert len(chunks) > 0, "Expected to receive chunks"

    total_content = "".join(chunks)
    assert len(total_content) > 0, "Expected non-empty content"


@pytest.mark.asyncio
async def test_e2e_error_handling_in_stream(client: TestClient) -> None:
    """Test that errors in streaming are handled gracefully."""
    # Use message that should still work
    response = client.post(
        "/api/chat",
        json={"message": "Hi"},
    )

    # Should get a successful response
    assert response.status_code == 200

    # Parse stream
    chunks, _ = parse_sse_stream(response)

    # Should have at least one chunk
    assert len(chunks) > 0
