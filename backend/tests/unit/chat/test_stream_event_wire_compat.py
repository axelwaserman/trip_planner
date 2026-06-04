"""Phase 6 / Plan 06-05a SSE wire-format golden file (renamed key, preserved order).

Per CONTEXT.md D-03 (Phase 6 session → conversation rename), the wire-level
correlation field on every ``StreamEvent`` subclass is now ``conversation_id``.
The Phase 4.7 wire-format invariant — the field stays declared on each
subclass and serialises LAST per concrete subclass — survives the rename:
the only delta vs the Phase 4.7/5 golden is the field NAME.

This file pins the post-rename golden bytes for the four happy-path events plus
``ErrorEvent`` (with the optional ``tool_name`` + ``raw_detail`` populated so
the order of every field is locked, including the optional ones).

Per VALIDATION.md row "SSE wire format (`model_dump_json()`) byte-equivalent"
— failure of any test below blocks Wave 5 sign-off. Plan 06-05b ships the
frontend rename in the SAME wave so the wire-format break atomic-PRs into
master.
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
    """ContentEvent.model_dump_json() emits ``conversation_id`` LAST."""
    event = ContentEvent(chunk="hi", conversation_id="s1")
    assert event.model_dump_json() == '{"type":"content","chunk":"hi","conversation_id":"s1"}'


def test_thinking_event_wire_unchanged() -> None:
    """ThinkingEvent.model_dump_json() emits ``conversation_id`` LAST."""
    event = ThinkingEvent(chunk="think", conversation_id="s1")
    assert event.model_dump_json() == '{"type":"thinking","chunk":"think","conversation_id":"s1"}'


def test_tool_call_event_wire_unchanged() -> None:
    """ToolCallEvent.model_dump_json() emits ``conversation_id`` LAST."""
    event = ToolCallEvent(
        tool_name="search_flights",
        tool_args={"origin": "LAX"},
        conversation_id="s1",
    )
    assert event.model_dump_json() == (
        '{"type":"tool_call","tool_name":"search_flights","tool_args":{"origin":"LAX"},"conversation_id":"s1"}'
    )


def test_tool_result_event_wire_unchanged() -> None:
    """ToolResultEvent.model_dump_json() emits ``conversation_id`` LAST."""
    event = ToolResultEvent(
        tool_name="search_flights",
        tool_result="ok",
        elapsed_ms=42,
        conversation_id="s1",
    )
    assert event.model_dump_json() == (
        '{"type":"tool_result","tool_name":"search_flights","tool_result":"ok",'
        '"elapsed_ms":42,"conversation_id":"s1"}'
    )


def test_error_event_wire_unchanged() -> None:
    """ErrorEvent.model_dump_json() emits ``conversation_id`` LAST.

    Captured with ``tool_name`` and ``raw_detail`` populated so the golden
    file pins the order of every field, including the optional ones.
    ``ErrorCode`` is a ``StrEnum``; its wire value is ``"tool_error"``
    (snake_case, immutable per CLAUDE.md "wire-level snake_case values are
    part of the contract").
    """
    event = ErrorEvent(
        error_code=ErrorCode.tool_error,
        message="boom",
        retryable=True,
        tool_name="search_flights",
        raw_detail="scrubbed",
        conversation_id="s1",
    )
    assert event.model_dump_json() == (
        '{"type":"error","error_code":"tool_error","message":"boom",'
        '"retryable":true,"tool_name":"search_flights",'
        '"raw_detail":"scrubbed","conversation_id":"s1"}'
    )
