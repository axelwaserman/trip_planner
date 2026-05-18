"""Integration tests for ChatService.chat_stream() — service layer (D-11) + HTTP layer."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.api.main import app
from app.models import FlightSearchResult
from tests.fixtures.llm import (
    MockLLMStream,
    default_session_config,
    make_chat_service_with_mock_llm,
)


@pytest.fixture
def client() -> Generator[TestClient]:
    """Create test client with FastAPI lifespan context."""
    with TestClient(app) as c:
        yield c


async def test_chat_stream_emits_tool_events_for_flight_query() -> None:
    """Single tool-call stream produces tool_call, tool_result, and content events."""
    # Arrange
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    # Act
    events = [e async for e in service.chat_stream("Find flights LAX to JFK", session_id)]

    # Assert — event types
    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "content" in types

    # Assert — tool_result shape
    tool_result_event = next(e for e in events if e.type == "tool_result")
    assert tool_result_event.elapsed_ms is not None
    assert isinstance(tool_result_event.elapsed_ms, int)
    assert tool_result_event.tool_name == "search_flights"

    # Assert — history: HumanMessage, AIMessage(tool_calls), ToolMessage, AIMessage
    history = service.get_session_history(session_id)
    msgs = list(history.messages)
    assert any(isinstance(m, HumanMessage) for m in msgs)
    assert any(isinstance(m, ToolMessage) for m in msgs)
    assert len([m for m in msgs if isinstance(m, AIMessage)]) == 2

    # Assert — tool_result.tool_result is valid FlightSearchResult JSON (REQ-tool-json-output)
    assert tool_result_event.tool_result is not None
    parsed = FlightSearchResult.model_validate_json(tool_result_event.tool_result)
    assert parsed.status == "ok"
    assert parsed.count >= 1
    assert parsed.query.origin == "LAX"


async def test_chat_stream_retains_history_across_turns() -> None:
    """Two sequential chat_stream() calls in one session produce 4 history messages."""
    # Arrange — one MockLLM with two inner stream lists (one per turn)
    service = make_chat_service_with_mock_llm(
        [
            *MockLLMStream.greeting(),  # first turn: one inner list of Content chunks
            *MockLLMStream.multi_turn(),  # second turn: one inner list of Content chunks
        ]
    )
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    # Act — drain both turns fully
    _ = [e async for e in service.chat_stream("Hello", session_id)]
    _ = [e async for e in service.chat_stream("Show me alternatives", session_id)]

    # Assert — 4 messages: HumanMessage, AIMessage, HumanMessage, AIMessage
    history = service.get_session_history(session_id)
    msgs = list(history.messages)
    assert len(msgs) == 4
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert isinstance(msgs[2], HumanMessage)
    assert isinstance(msgs[3], AIMessage)


async def test_post_chat_streams_tool_events_via_mock_llm(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """HTTP layer: POST /api/chat with MockLLM injected produces tool event SSE stream."""
    # Arrange — replace app.state.chat_service BEFORE the POST
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    client.app.state.chat_service = service  # type: ignore[attr-defined]
    session_id, _ = await service.create_session(default_session_config(), user_id="admin")

    # Act
    response = client.post(
        "/api/chat",
        json={"message": "Find flights", "session_id": session_id},
        headers=auth_headers,
    )

    # Assert — HTTP + SSE shape
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    body = response.text
    assert '"type":"tool_call"' in body
    assert '"type":"tool_result"' in body
    assert '"type":"content"' in body
