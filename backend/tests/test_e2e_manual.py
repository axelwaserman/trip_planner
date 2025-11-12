"""Manual E2E tests to verify agent behavior with real LLM.

Run with: pytest tests/test_e2e_manual.py -v -s

These tests make actual LLM calls and verify conversation flow.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


def parse_sse_stream(response) -> tuple[list[str], str | None]:
    """Parse Server-Sent Events stream and extract chunks and session_id."""
    chunks = []
    session_id = None
    errors = []

    for line in response.iter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if "chunk" in data:
                chunks.append(data["chunk"])
            if "session_id" in data:
                session_id = data["session_id"]
            if "error" in data:
                errors.append(data["error"])
            if data.get("done"):
                break

    if errors:
        print(f"ERRORS IN STREAM: {errors}")

    return chunks, session_id


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_simple_flight_search(client: TestClient) -> None:
    """Test: Find flights from LAX to JFK on June 15th 2025."""
    response = client.post(
        "/api/chat",
        json={"message": "Find flights from LAX to JFK on June 15th 2025"},
    )

    chunks, session_id = parse_sse_stream(response)
    full_response = "".join(chunks).lower()

    print("\n=== SIMPLE FLIGHT SEARCH ===")
    print(f"Response: {full_response[:500]}...")
    
    # Should mention flights and show results
    assert "flight" in full_response, "Expected flight information"
    assert any(word in full_response for word in ["lax", "jfk"]), "Expected airport codes"
    assert any(word in full_response for word in ["$", "price", "airline"]), "Expected flight details"


def test_conversation_memory_simple(client: TestClient) -> None:
    """Test: Remember name across messages."""
    # First message
    response1 = client.post(
        "/api/chat",
        json={"message": "My name is Sarah. Please remember that."},
    )
    chunks1, session_id = parse_sse_stream(response1)
    response1_text = "".join(chunks1)
    
    print("\n=== MEMORY TEST - First Message ===")
    print(f"Session ID: {session_id}")
    print(f"Response: {response1_text[:300]}...")
    
    assert session_id is not None, "Session ID should not be None"

    # Second message - ask about name
    print(f"\n=== MEMORY TEST - Sending second message with session: {session_id} ===")
    response2 = client.post(
        "/api/chat",
        json={"message": "What is my name?", "session_id": session_id},
    )
    chunks2, session_id2 = parse_sse_stream(response2)
    response2_text = "".join(chunks2).lower()
    
    print(f"Session ID 2: {session_id2}")
    print(f"Response: {response2_text[:300] if response2_text else '(EMPTY)'}...")
    print(f"Full response: {response2_text}")

    # Should remember the name
    assert len(response2_text) > 0, "Response should not be empty"
    assert "sarah" in response2_text, f"Expected to remember name 'Sarah' in: {response2_text}"


def test_followup_on_flight_search(client: TestClient) -> None:
    """Test: Ask follow-up question about previous search."""
    # First: Search flights
    response1 = client.post(
        "/api/chat",
        json={"message": "Find flights from LAX to JFK on June 15th 2025"},
    )
    chunks1, session_id = parse_sse_stream(response1)
    response1_text = "".join(chunks1)
    
    print("\n=== FOLLOW-UP TEST - Initial Search ===")
    print(f"Response: {response1_text[:500]}...")
    
    assert session_id is not None
    assert "flight" in response1_text.lower()

    # Second: Ask about cheapest
    response2 = client.post(
        "/api/chat",
        json={"message": "Which one is the cheapest?", "session_id": session_id},
    )
    chunks2, _ = parse_sse_stream(response2)
    response2_text = "".join(chunks2).lower()
    
    print("\n=== FOLLOW-UP TEST - Cheapest Question ===")
    print(f"Response: {response2_text[:500]}...")

    # Should reference the previous search
    assert len(response2_text) > 0
    # Should mention price or specific flight
    assert any(word in response2_text for word in ["cheap", "price", "$", "lowest", "flight"])


def test_city_name_inference(client: TestClient) -> None:
    """Test: Los Angeles to New York (should infer LAX and JFK)."""
    response = client.post(
        "/api/chat",
        json={"message": "Show me flights from Los Angeles to New York on December 1st 2025"},
    )

    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks).lower()

    print("\n=== CITY NAME INFERENCE ===")
    print(f"Response: {full_response[:500]}...")
    
    # Should call tool and show flights (LLM should infer LAX and JFK)
    assert "flight" in full_response, "Expected flight results"
    # Should mention Los Angeles/LA or LAX, and New York/NY or JFK
    assert any(word in full_response for word in ["los angeles", "lax", "la"]), "Expected LA reference"
    assert any(word in full_response for word in ["new york", "jfk", "ny"]), "Expected NY reference"


def test_multiple_dates(client: TestClient) -> None:
    """Test: Flights work for different dates (December 2025, January 2026)."""
    dates = [
        "December 20th 2025",
        "January 10th 2026",
        "February 14th 2026",
    ]
    
    for test_date in dates:
        response = client.post(
            "/api/chat",
            json={"message": f"Find flights from SFO to SEA on {test_date}"},
        )
        
        chunks, _ = parse_sse_stream(response)
        full_response = "".join(chunks).lower()
        
        print(f"\n=== DATE TEST: {test_date} ===")
        print(f"Response: {full_response[:300]}...")
        
        # Should find flights for any date
        assert "flight" in full_response, f"Expected flights for {test_date}"
        assert any(word in full_response for word in ["sfo", "sea"]), f"Expected airport codes for {test_date}"


def test_no_tool_for_general_chat(client: TestClient) -> None:
    """Test: General conversation should not trigger flight tool."""
    response = client.post(
        "/api/chat",
        json={"message": "What's the weather like today?"},
    )

    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks).lower()

    print("\n=== GENERAL CHAT (NO TOOL) ===")
    print(f"Response: {full_response[:300]}...")
    
    # Should respond but not search for flights
    assert len(full_response) > 0
    # Should NOT show the flight search indicator
    assert "searching for flights" not in full_response


def test_ambiguous_location_handling(client: TestClient) -> None:
    """Test: Ambiguous location should ask for clarification or make reasonable inference."""
    response = client.post(
        "/api/chat",
        json={"message": "Find flights from a seaside city to Orlando on June 1st 2025"},
    )

    chunks, _ = parse_sse_stream(response)
    full_response = "".join(chunks).lower()

    print("\n=== AMBIGUOUS LOCATION ===")
    print(f"Response: {full_response[:500]}...")
    
    # Should either ask for clarification OR make a reasonable inference
    # Looking for signs it's handling the ambiguity properly
    assert len(full_response) > 0
    # Should either ask which city, or pick a common seaside city
    valid_responses = [
        "which" in full_response,  # Asking which city
        "clarif" in full_response,  # Asking for clarification
        "specific" in full_response,  # Asking for specific city
        "miami" in full_response,  # Inferred Miami
        "san diego" in full_response,  # Inferred San Diego
        "los angeles" in full_response,  # Inferred LA
    ]
    assert any(valid_responses), f"Expected clarification or inference, got: {full_response[:200]}"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
