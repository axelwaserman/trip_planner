"""Wave 0 RED stub: agent.iter() event-loop → StreamEvent mapping (D-12).

Per CONTEXT.md D-12 + RESEARCH §3 streaming + §Stream Event Type Map, the Phase 5
``ChatService.chat_stream()`` walks ``async with agent.iter(...) as agent_run``,
matching PydanticAI ``PartStartEvent`` / ``PartDeltaEvent`` / ``FunctionToolResultEvent``
into the four concrete StreamEvent subclasses:

    ThinkingPart / ThinkingPartDelta → ThinkingEvent
    TextPart     / TextPartDelta     → ContentEvent
    ToolCallPart                     → ToolCallEvent
    FunctionToolResultEvent          → ToolResultEvent

These tests use the rewritten ``make_chat_service_with_mock_llm`` fixture
(``backend/tests/fixtures/llm.py`` — Phase 5 swap from ``MockLLM(BaseChatModel)``
to ``FunctionModel(stream_function=...)``). The fixture rewrite lands in Wave 1;
until then, this file collects via the existing fixture import path and the
tests fail RED on the missing PydanticAI substrate.

Analog: ``backend/tests/unit/test_chat_stream.py:18-36`` (greeting test).
"""

import pytest
from pydantic_ai.messages import FunctionToolResultEvent, RetryPromptPart

from app.chat.models import ErrorCode, ErrorEvent

# Wave 1 rewrites tests/fixtures/llm.py to provide the PydanticAI-shaped
# fixture. Until then, importing the fixture itself is fine; what fails RED
# is the call into the rewritten ChatService internals (which currently still
# uses LangChain's astream, not agent.iter()).
fixtures_llm = pytest.importorskip("tests.fixtures.llm")
make_chat_service_with_mock_llm = fixtures_llm.make_chat_service_with_mock_llm
default_session_config = fixtures_llm.default_session_config
MockLLMStream = fixtures_llm.MockLLMStream
Content = fixtures_llm.Content
Thinking = fixtures_llm.Thinking
ToolCall = fixtures_llm.ToolCall


async def test_thinking() -> None:
    """A Thinking chunk in the mock stream surfaces as a ``ThinkingEvent``."""
    streams = [[Thinking("planning your trip"), Content("Hello!")]]
    service = make_chat_service_with_mock_llm(streams)
    session_id, _ = await service.create_session(default_session_config(), user_id="u")
    events = [e async for e in service.chat_stream("hi", session_id)]
    types = [e.type for e in events]
    assert "thinking" in types


async def test_text() -> None:
    """A Content chunk in the mock stream surfaces as a ``ContentEvent``."""
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="u")
    events = [e async for e in service.chat_stream("Hello", session_id)]
    types = [e.type for e in events]
    assert "content" in types


async def test_tool_call() -> None:
    """A ToolCall chunk surfaces as a ``ToolCallEvent`` (before the tool runs)."""
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    session_id, _ = await service.create_session(default_session_config(), user_id="u")
    events = [e async for e in service.chat_stream("Find flights LAX-JFK", session_id)]
    types = [e.type for e in events]
    assert "tool_call" in types


async def test_tool_result() -> None:
    """A FunctionToolResultEvent (post-tool-execution) surfaces as ``ToolResultEvent``.

    The single_tool_call scenario produces a ``tool_call`` then runs the
    real ``search_flights`` tool against the ``MockFlightAPIClient``, so
    a ``tool_result`` event is yielded with the tool's JSON payload.
    """
    service = make_chat_service_with_mock_llm(MockLLMStream.single_tool_call())
    session_id, _ = await service.create_session(default_session_config(), user_id="u")
    events = [e async for e in service.chat_stream("Find flights LAX-JFK", session_id)]
    types = [e.type for e in events]
    assert "tool_result" in types


async def test_retry_prompt_part_yields_error_event() -> None:
    """C4: ``FunctionToolResultEvent`` wrapping ``RetryPromptPart`` → ``ErrorEvent``.

    ``_handle_tool_event`` must yield an ``ErrorEvent`` (error_code=tool_error,
    retryable=True) when the tool result carries a ``RetryPromptPart`` rather
    than a ``ToolReturnPart``. Before C4 this branch was unhandled; the
    ``RetryPromptPart`` fell through the isinstance checks silently.

    This test calls ``_handle_tool_event`` directly because the FunctionModel
    fixture has no way to produce a ``RetryPromptPart`` response from a tool
    (PydanticAI only creates those internally when a tool raises
    ``ModelRetry``). Direct invocation of the private helper is intentional —
    it is the minimal unit that covers the branch.
    """
    # Arrange — construct the raw PydanticAI event the helper receives
    retry_part = RetryPromptPart(
        content="search_flights returned an error; please retry",
        tool_name="search_flights",
        tool_call_id="tc-test-001",
    )
    event = FunctionToolResultEvent(part=retry_part)

    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="u")
    tool_call_start: dict[str, float] = {"tc-test-001": 0.0}

    # Act — consume the async generator from _handle_tool_event
    emitted = [ev async for ev in service._handle_tool_event(event, session_id, tool_call_start)]

    # Assert — exactly one ErrorEvent; timing entry cleaned up (no memory leak)
    assert len(emitted) == 1
    assert isinstance(emitted[0], ErrorEvent)
    assert emitted[0].error_code == ErrorCode.tool_error
    assert emitted[0].retryable is True
    assert emitted[0].tool_name == "search_flights"
    assert "tc-test-001" not in tool_call_start  # timing entry cleaned up
