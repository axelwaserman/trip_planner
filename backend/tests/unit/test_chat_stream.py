"""Unit tests for ChatService.chat_stream() with the FunctionModel-backed mock.

Phase 5 / Plan 05-04 (Wave 3): the LangChain-shape tests that patched
``search_flights.ainvoke`` to inject errors retire here. The Phase 4.7
contract — ``ErrorEvent.error_code`` taxonomy + ``raw_detail`` scrubbing —
is preserved by the rewritten ``ChatService.chat_stream`` exception handler;
the new tests trigger errors via the ``FunctionModel.stream_function``
substrate (the ``streams: Callable[[], None]`` widening on
``make_chat_service_with_mock_llm``) instead of patching the tool surface.

Greeting/content scenarios continue to drive the fixture's ``MockLLMStream``
classmethods unchanged. History assertions migrate from
``service.get_session_history(session_id).messages`` to
``await service._conversation_store.load(session_id)``.
"""

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.chat.models import ErrorCode, ErrorEvent
from tests.fixtures.llm import (
    MockLLMStream,
    default_session_config,
    make_chat_service_with_mock_llm,
)


async def test_chat_stream_emits_content_events_for_greeting() -> None:
    """Content-only mock stream produces only 'content' type events and correct history."""
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("Hello", session_id)]

    content_events = [e for e in events if e.type == "content"]
    non_content_events = [e for e in events if e.type not in ("content",)]
    assert len(content_events) >= 1
    assert len(non_content_events) == 0

    # History: one ModelRequest (with UserPromptPart) and one ModelResponse (with TextPart).
    msgs = await service._conversation_store.load(session_id)
    user_msgs = [p for m in msgs if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, UserPromptPart)]
    assistant_msgs = [p for m in msgs if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, TextPart)]
    assert len(user_msgs) == 1
    assert str(user_msgs[0].content) == "Hello"
    assert len(assistant_msgs) == 1


async def test_chat_stream_yields_error_event_on_stream_exception() -> None:
    """Generic Exception in stream_function → ErrorEvent(stream_error, retryable=False).

    Phase 5 substitute for the Phase 4.7 ``test_chat_stream_yields_error_event_on_tool_unexpected_exception``
    test: that test patched ``search_flights.ainvoke`` (a LangChain-only surface)
    to raise a plain Exception; the equivalent under PydanticAI is to inject
    the failure at the ``FunctionModel.stream_function`` level (the contract
    documented in ``tests/unit/chat/test_stream_error_event.py`` and the
    ``StreamsArg`` widening on ``make_chat_service_with_mock_llm``).
    """

    def boom() -> None:
        raise RuntimeError("kaboom")

    service = make_chat_service_with_mock_llm(boom)  # type: ignore[arg-type]
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("find flights", session_id)]

    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1
    err = error_events[0]
    assert isinstance(err, ErrorEvent)
    assert err.error_code == ErrorCode.stream_error
    assert err.retryable is False
    assert err.raw_detail is not None
    assert "kaboom" in (err.raw_detail or "")


async def test_chat_stream_scrubs_api_key_from_raw_detail() -> None:
    """``ErrorEvent.raw_detail`` is passed through ``_scrub`` (Phase 4.7 contract).

    Same invariant as ``tests/unit/chat/test_stream_error_event.py`` but under
    a ``RuntimeError`` instead of an ``APIError``: the ``_scrub`` function must
    rewrite ``sk-proj-...`` patterns to ``sk-[REDACTED]`` regardless of the
    exception subclass.
    """
    fake_key = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"

    def boom() -> None:
        raise RuntimeError(f"call to OpenAI failed: {fake_key}")

    service = make_chat_service_with_mock_llm(boom)  # type: ignore[arg-type]
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("find flights", session_id)]

    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1
    err = error_events[0]
    assert err.raw_detail is not None
    assert fake_key not in (err.raw_detail or "")
    assert "sk-[REDACTED]" in (err.raw_detail or "")


@pytest.mark.parametrize(
    "scenario_name",
    ["greeting", "multi_turn"],
)
async def test_chat_stream_no_tool_call_for_content_scenarios(scenario_name: str) -> None:
    """Content-only scenarios never produce tool_call / tool_result events."""
    scenario = getattr(MockLLMStream, scenario_name)()
    service = make_chat_service_with_mock_llm(scenario)
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    events = [e async for e in service.chat_stream("hi", session_id)]
    types = {e.type for e in events}
    assert "tool_call" not in types
    assert "tool_result" not in types
