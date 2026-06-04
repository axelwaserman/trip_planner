"""Integration tests: three locked MockLLMStream scenarios drive ChatService.

Phase 5 / Plan 05-04 (Wave 3): exercises the rewritten
``make_chat_service_with_mock_llm`` fixture (FunctionModel-backed PydanticAI
``Agent``) end-to-end, asserting that each scenario produces the expected
StreamEvent types in order. Per CONTEXT.md D-17 + D-19 the scenarios are
locked: ``greeting`` → content-only; ``single_tool_call`` →
content/tool_call/tool_result; ``multi_turn`` → content-only with prior-turn
reference.

Tests run offline — no ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` /
``OLLAMA_BASE_URL`` required.
"""

from app.flights.models import FlightSearchResult
from tests.fixtures.llm import (
    MockLLMStream,
    default_session_config,
    make_chat_service_with_mock_llm,
)


async def test_greeting() -> None:
    """``greeting`` scenario emits content events only (no tool calls)."""
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("Hello", conversation_id)]
    types = [e.type for e in events]

    assert "content" in types
    assert "tool_call" not in types
    assert "tool_result" not in types


async def test_single_tool_call() -> None:
    """``single_tool_call`` scenario emits tool_call → tool_result → content."""
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("Find flights LAX to JFK", conversation_id)]
    types = [e.type for e in events]

    assert "tool_call" in types
    assert "tool_result" in types
    assert "content" in types

    # The tool_call must precede the tool_result; the tool_result must precede
    # the post-tool content event (the "summary" Content from Pitfall 7's
    # second inner stream list).
    tool_call_idx = types.index("tool_call")
    tool_result_idx = types.index("tool_result")
    first_content_idx = next(i for i, t in enumerate(types) if t == "content")
    assert tool_call_idx < tool_result_idx
    assert tool_result_idx < first_content_idx

    # The tool_result body is a valid FlightSearchResult JSON envelope
    # (REQ-tool-json-output preserved from Phase 4.6).
    tool_result_event = next(e for e in events if e.type == "tool_result")
    assert tool_result_event.tool_name == "search_flights"
    assert isinstance(tool_result_event.elapsed_ms, int)
    assert tool_result_event.elapsed_ms >= 0
    parsed = FlightSearchResult.model_validate_json(tool_result_event.tool_result)
    assert parsed.status == "ok"
    assert parsed.count >= 1
    assert parsed.query.origin == "LAX"


async def test_multi_turn() -> None:
    """``multi_turn`` scenario emits content events; assistant references prior turn."""
    service = make_chat_service_with_mock_llm(MockLLMStream.multi_turn())
    conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("Show me alternatives", conversation_id)]
    types = [e.type for e in events]

    assert "content" in types
    assert "tool_call" not in types
