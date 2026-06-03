"""Phase 4.7 → Phase 5 SSE wire-format byte-equivalence golden file.

Per CONTEXT.md D-15, the StreamEvent ABC refactor in Wave 1 must NOT change the
SSE wire bytes that the frontend parses. Per RESEARCH OQ-01, switching the
``StreamEvent`` alias to a real ``BaseModel + ABC`` base class is byte-equivalent
when each subclass keeps its ``Literal[...]`` discriminator and preserves field
order.

This file is deliberately captured BEFORE the refactor lands. The five golden
strings below are the literal output of ``model_dump_json()`` against the
current Phase 4.7 production classes — they ARE the Phase 4.7 wire reference.
After Wave 1's refactor, these tests must continue to pass byte-for-byte. If
they break, the refactor regressed the wire contract and the frontend will
mis-parse events.

The expected strings reflect the current Phase 4.7 field ordering, which puts
``session_id`` LAST on the four "happy-path" events and on ``ErrorEvent``. The
Wave 1 refactor (which hoists ``session_id`` into the base class) must
preserve that final-position serialisation; if Pydantic surfaces a different
order, the implementation must use ``model_config`` / ``Field(...)`` knobs to
match.

Per VALIDATION.md row "SSE wire format (`model_dump_json()`) byte-equivalent
to Phase 4.7" — failure of any test below blocks Wave 1 sign-off.
"""

from app.chat.models import (
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def test_content_event_wire_unchanged() -> None:
    """ContentEvent.model_dump_json() matches the Phase 4.7 reference bytes."""
    event = ContentEvent(chunk="hi", session_id="s1")
    assert event.model_dump_json() == '{"type":"content","chunk":"hi","session_id":"s1"}'


def test_thinking_event_wire_unchanged() -> None:
    """ThinkingEvent.model_dump_json() matches the Phase 4.7 reference bytes."""
    event = ThinkingEvent(chunk="think", session_id="s1")
    assert event.model_dump_json() == '{"type":"thinking","chunk":"think","session_id":"s1"}'


def test_tool_call_event_wire_unchanged() -> None:
    """ToolCallEvent.model_dump_json() matches the Phase 4.7 reference bytes."""
    event = ToolCallEvent(
        tool_name="search_flights",
        tool_args={"origin": "LAX"},
        session_id="s1",
    )
    assert event.model_dump_json() == (
        '{"type":"tool_call","tool_name":"search_flights","tool_args":{"origin":"LAX"},"session_id":"s1"}'
    )


def test_tool_result_event_wire_unchanged() -> None:
    """ToolResultEvent.model_dump_json() matches the Phase 4.7 reference bytes."""
    event = ToolResultEvent(
        tool_name="search_flights",
        tool_result="ok",
        elapsed_ms=42,
        session_id="s1",
    )
    assert event.model_dump_json() == (
        '{"type":"tool_result","tool_name":"search_flights","tool_result":"ok","elapsed_ms":42,"session_id":"s1"}'
    )


def test_error_event_wire_unchanged() -> None:
    """ErrorEvent.model_dump_json() matches the Phase 4.7 reference bytes.

    Captured with ``tool_name`` and ``raw_detail`` populated so the golden file
    pins the order of every field, including the optional ones. ``ErrorCode``
    is a ``StrEnum``; its wire value is ``"tool_error"`` (snake_case, immutable
    per CLAUDE.md "wire-level snake_case values are part of the contract").
    """
    event = ErrorEvent(
        error_code=ErrorCode.tool_error,
        message="boom",
        retryable=True,
        tool_name="search_flights",
        raw_detail="scrubbed",
        session_id="s1",
    )
    assert event.model_dump_json() == (
        '{"type":"error","error_code":"tool_error","message":"boom",'
        '"retryable":true,"tool_name":"search_flights",'
        '"raw_detail":"scrubbed","session_id":"s1"}'
    )
