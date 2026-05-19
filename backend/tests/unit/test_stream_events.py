"""Unit tests for the discriminated-union StreamEvent hierarchy (Phase 4.7 Plan 01).

Tests the 5 concrete event models (ContentEvent, ThinkingEvent, ToolCallEvent,
ToolResultEvent, ErrorEvent), the ErrorCode StrEnum, and the StreamEvent
discriminated-union alias introduced by app.chat.models.

These tests are in the RED state before Task 2 creates app/chat/models.py.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.chat.models import (
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    StreamEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.llm.log_scrubbing import _scrub


# ---------------------------------------------------------------------------
# Test 1: ErrorCode StrEnum
# ---------------------------------------------------------------------------


def test_error_code_is_strenum_with_three_members() -> None:
    """ErrorCode must be a StrEnum with the three wire-level snake_case members."""
    # Members exist
    assert ErrorCode.session_error == "session_error"
    assert ErrorCode.tool_error == "tool_error"
    assert ErrorCode.stream_error == "stream_error"

    # StrEnum values are str subclasses (assertable via isinstance)
    assert isinstance(ErrorCode.session_error, str)
    assert isinstance(ErrorCode.tool_error, str)
    assert isinstance(ErrorCode.stream_error, str)

    # Exactly three members
    assert len(ErrorCode) == 3


# ---------------------------------------------------------------------------
# Test 2: Each event model instantiates and serialises with the correct
#          discriminator key.
# ---------------------------------------------------------------------------


def test_event_models_instantiate_and_serialise_with_discriminator() -> None:
    """All five event models serialise with the correct 'type' discriminator."""
    content = ContentEvent(chunk="hello", session_id="s1")
    assert '"type":"content"' in content.model_dump_json()

    thinking = ThinkingEvent(chunk="reasoning", session_id="s1")
    assert '"type":"thinking"' in thinking.model_dump_json()

    tool_call = ToolCallEvent(tool_name="search_flights", tool_args={"origin": "LAX"}, session_id="s1")
    assert '"type":"tool_call"' in tool_call.model_dump_json()

    tool_result = ToolResultEvent(
        tool_name="search_flights", tool_result="5 flights found", elapsed_ms=123, session_id="s1"
    )
    assert '"type":"tool_result"' in tool_result.model_dump_json()

    error = ErrorEvent(
        error_code=ErrorCode.tool_error,
        message="Tool failed.",
        retryable=True,
        session_id="s1",
    )
    assert '"type":"error"' in error.model_dump_json()


# ---------------------------------------------------------------------------
# Test 3: ToolCallEvent and ToolResultEvent reject construction without
#          required fields.
# ---------------------------------------------------------------------------


def test_tool_call_event_rejects_construction_without_required_fields() -> None:
    """ToolCallEvent requires tool_name and tool_args (Pydantic ValidationError)."""
    with pytest.raises(ValidationError):
        ToolCallEvent(session_id="s1")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ToolCallEvent(tool_name="search_flights", session_id="s1")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ToolCallEvent(tool_args={"origin": "LAX"}, session_id="s1")  # type: ignore[call-arg]


def test_tool_result_event_rejects_construction_without_required_fields() -> None:
    """ToolResultEvent requires tool_name, tool_result, and elapsed_ms."""
    with pytest.raises(ValidationError):
        ToolResultEvent(session_id="s1")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ToolResultEvent(tool_name="search_flights", session_id="s1")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ToolResultEvent(tool_name="search_flights", tool_result="x", session_id="s1")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Test 4: ErrorEvent rejects construction without required fields.
# ---------------------------------------------------------------------------


def test_error_event_rejects_construction_without_required_fields() -> None:
    """ErrorEvent requires error_code, message, retryable, and session_id."""
    # Missing all required fields
    with pytest.raises(ValidationError):
        ErrorEvent()  # type: ignore[call-arg]

    # Missing session_id
    with pytest.raises(ValidationError):
        ErrorEvent(error_code=ErrorCode.tool_error, message="x", retryable=True)  # type: ignore[call-arg]

    # tool_name and raw_detail are optional — construction with just the required
    # fields must succeed.
    event = ErrorEvent(
        error_code=ErrorCode.tool_error,
        message="x",
        retryable=False,
        session_id="s1",
    )
    assert event.tool_name is None
    assert event.raw_detail is None


# ---------------------------------------------------------------------------
# Test 5: StreamEvent union alias deserialises via TypeAdapter.
# ---------------------------------------------------------------------------


def test_stream_event_union_alias_deserialises_error_event() -> None:
    """TypeAdapter(StreamEvent) must deserialise an error payload to ErrorEvent."""
    payload = {
        "type": "error",
        "error_code": "tool_error",
        "message": "x",
        "retryable": True,
        "session_id": "s",
    }
    adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)
    result = adapter.validate_python(payload)
    assert isinstance(result, ErrorEvent)
    assert result.error_code == ErrorCode.tool_error


def test_stream_event_union_alias_deserialises_content_event() -> None:
    """TypeAdapter(StreamEvent) must deserialise a content payload to ContentEvent."""
    payload = {"type": "content", "chunk": "hi", "session_id": "s"}
    adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)
    result = adapter.validate_python(payload)
    assert isinstance(result, ContentEvent)
    assert result.chunk == "hi"


# ---------------------------------------------------------------------------
# Test 6: raw_detail scrubbing — integration shape (scrubbing happens at
#          construction sites in service.py; this test asserts the shape).
# ---------------------------------------------------------------------------


def test_error_event_raw_detail_is_scrubbed() -> None:
    """_scrub() applied to str(exc) before passing as raw_detail strips sk- keys.

    This test documents the expected integration: service.py calls
    _scrub(str(exc)) and passes the result as raw_detail. The scrubber must
    replace sk-proj-... keys with 'sk-[REDACTED]'.
    """
    # Arrange: a string that would come from str(exc) in a real exception
    exc_text = "api call with sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA failed"

    # Act: apply the scrubber the same way service.py will
    scrubbed = _scrub(exc_text)

    # Assert: the key-shaped substring is redacted
    assert "sk-[REDACTED]" in scrubbed
    assert "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA" not in scrubbed

    # Construct the event with the scrubbed detail — must succeed
    event = ErrorEvent(
        error_code=ErrorCode.tool_error,
        message="Tool failed.",
        retryable=False,
        raw_detail=scrubbed,
        session_id="s1",
    )
    assert event.raw_detail is not None
    assert "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA" not in event.raw_detail
    assert "sk-[REDACTED]" in event.raw_detail
    assert ErrorCode.session_error is not None  # Ensure all three members importable
