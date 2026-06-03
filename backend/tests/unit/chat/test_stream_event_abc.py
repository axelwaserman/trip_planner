"""Wave 0 RED stub: StreamEvent ABC golden test (D-15 + RESEARCH OQ-01).

Per CONTEXT.md D-15 + D-16, the Phase 4.7 ``Annotated[..., Field(discriminator=
"type")]`` alias is replaced with a real ``class StreamEvent(BaseModel, ABC)``
base class. RESEARCH OQ-01 confirms the ABC marker without ``@abstractmethod``
keeps Pydantic discriminator round-trips intact.

Today (Wave 0) ``StreamEvent`` is still the union alias from Phase 4.7 — the
``inspect.isabstract`` and "is ABC" assertions WILL FAIL until Wave 1's
refactor lands. The ``isinstance(...)`` assertions WILL ALSO FAIL today
because the union alias does not satisfy ``isinstance`` checks. That's the
expected RED state.
"""

import inspect
import typing

from pydantic import TypeAdapter

from app.chat.models import (
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    StreamEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def test_streamevent_is_abc() -> None:
    """StreamEvent is an ``abc.ABC`` subclass after Wave 1 (D-15 / OQ-01).

    ``inspect.isabstract`` returns True for classes that subclass ABC AND
    have at least one abstract method, OR for classes whose ``__abstractmethods__``
    is non-empty. Per RESEARCH OQ-01, StreamEvent has NO abstract methods
    (it's an "ABC marker for isinstance"), so ``isinstance(StreamEvent, ABCMeta)``
    is the more precise assertion.
    """
    from abc import ABCMeta

    assert isinstance(StreamEvent, ABCMeta)


def test_concrete_event_isinstance_streamevent_abc() -> None:
    """Each of the 5 concrete subclasses is an ``isinstance`` of StreamEvent."""
    assert isinstance(ContentEvent(chunk="hi", session_id="s"), StreamEvent)
    assert isinstance(ThinkingEvent(chunk="think", session_id="s"), StreamEvent)
    assert isinstance(
        ToolCallEvent(tool_name="search_flights", tool_args={}, session_id="s"),
        StreamEvent,
    )
    assert isinstance(
        ToolResultEvent(
            tool_name="search_flights", tool_result="ok", elapsed_ms=1, session_id="s"
        ),
        StreamEvent,
    )
    assert isinstance(
        ErrorEvent(
            error_code=ErrorCode.tool_error,
            message="x",
            retryable=False,
            session_id="s",
        ),
        StreamEvent,
    )


def test_typeadapter_round_trip() -> None:
    """TypeAdapter(StreamEvent) deserialises a discriminator payload to ErrorEvent."""
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


def test_streamevent_is_not_a_protocol() -> None:
    """StreamEvent is an ABC, never a typing.Protocol (CLAUDE.md "ABC over Protocol")."""
    # typing.Protocol's metaclass is _ProtocolMeta; StreamEvent must NOT use it.
    assert not isinstance(StreamEvent, type(typing.Protocol))
