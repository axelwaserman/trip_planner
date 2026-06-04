"""Integration tests for ChatService.chat_stream() — service layer (D-11) + HTTP layer.

Phase 5 / Plan 05-04 (Wave 3): the LangChain history assertions
(``isinstance(m, HumanMessage)`` / ``ToolMessage`` / ``AIMessage`` against
``service.get_session_history(session_id).messages``) are rewritten against the
:class:`ConversationStore` seam — ``await store.load(session_id)`` returns
``list[ModelMessage]`` whose parts are PydanticAI's
:class:`UserPromptPart` / :class:`TextPart` / :class:`ToolCallPart` /
:class:`ToolReturnPart`. The semantic assertions are unchanged ("exactly two
ModelResponse entries with text or tool-call parts" replaces "exactly two
AIMessages").
"""

from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.api.main import app
from app.flights.models import FlightSearchResult
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
    """Single tool-call stream produces tool_call, tool_result, and content events.

    History assertion (rewritten): the ``ConversationStore`` returns a
    ``list[ModelMessage]`` containing exactly two ``ModelResponse`` entries
    (one with a ``ToolCallPart``, one with a ``TextPart``), one
    ``ModelRequest`` whose first part is a ``UserPromptPart`` carrying the
    user message, and a ``ToolReturnPart`` somewhere in the run's messages.
    """
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("Find flights LAX to JFK", session_id)]

    # Event-type assertions (unchanged from Phase 4.7).
    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "content" in types

    tool_result_event = next(e for e in events if e.type == "tool_result")
    assert tool_result_event.elapsed_ms is not None
    assert isinstance(tool_result_event.elapsed_ms, int)
    assert tool_result_event.tool_name == "search_flights"

    # tool_result.tool_result is a valid FlightSearchResult JSON envelope.
    parsed = FlightSearchResult.model_validate_json(tool_result_event.tool_result)
    assert parsed.status == "ok"
    assert parsed.count >= 1
    assert parsed.query.origin == "LAX"

    # History assertions: the ConversationStore returns PydanticAI's ModelMessage list.
    msgs = await service._message_store.load(UUID(session_id))
    assert any(
        isinstance(m, ModelRequest)
        and any(isinstance(p, UserPromptPart) and p.content == "Find flights LAX to JFK" for p in m.parts)
        for m in msgs
    ), "expected a ModelRequest with the user prompt"
    assert any(isinstance(m, ModelRequest) and any(isinstance(p, ToolReturnPart) for p in m.parts) for m in msgs), (
        "expected a ToolReturnPart in some ModelRequest"
    )

    # Phase 4.7 asserted "exactly 2 AIMessages" — semantic equivalence:
    # exactly 2 ModelResponse entries (one for the tool-call decision, one for the summary).
    response_msgs = [m for m in msgs if isinstance(m, ModelResponse)]
    assert len(response_msgs) == 2

    # The two ModelResponse entries carry, between them, both a ToolCallPart and a TextPart.
    has_tool_call = any(any(isinstance(p, ToolCallPart) for p in m.parts) for m in response_msgs)
    has_text = any(any(isinstance(p, TextPart) for p in m.parts) for m in response_msgs)
    assert has_tool_call, "expected a ToolCallPart in some ModelResponse"
    assert has_text, "expected a TextPart in some ModelResponse"


async def test_chat_stream_retains_history_across_turns() -> None:
    """Two sequential chat_stream() calls in one session preserve history.

    Phase 5 semantic equivalent of Phase 4.7's "4 history messages, alternating
    HumanMessage / AIMessage": after two content-only turns we should see two
    ``ModelRequest`` entries (each carrying a ``UserPromptPart``) and two
    ``ModelResponse`` entries (each carrying a ``TextPart``).
    """
    service = make_chat_service_with_mock_llm(
        [
            *MockLLMStream.greeting(),  # first turn
            *MockLLMStream.multi_turn(),  # second turn
        ]
    )
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    _ = [e async for e in service.chat_stream("Hello", session_id)]
    _ = [e async for e in service.chat_stream("Show me alternatives", session_id)]

    msgs = await service._message_store.load(UUID(session_id))

    user_prompts = [p for m in msgs if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, UserPromptPart)]
    assistant_texts = [p for m in msgs if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, TextPart)]

    assert len(user_prompts) == 2
    assert {str(p.content) for p in user_prompts} == {"Hello", "Show me alternatives"}
    assert len(assistant_texts) == 2


async def test_post_chat_streams_tool_events_via_mock_llm(client: TestClient, auth_headers: dict[str, str]) -> None:
    """HTTP layer: POST /api/chat with MockLLM injected produces tool event SSE stream."""
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    client.app.state.chat_service = service  # type: ignore[attr-defined]
    session_id, _ = await service.create_session(default_session_config(), user_id="admin")

    response = client.post(
        "/api/chat",
        json={"message": "Find flights", "session_id": session_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    body = response.text
    assert '"type":"tool_call"' in body
    assert '"type":"tool_result"' in body
    assert '"type":"content"' in body
