"""Unit tests for parse_sse_events helper."""

import json

import pytest
from pydantic import ValidationError

from app.chat.models import ContentEvent, StreamEvent
from tests.utils.sse import parse_sse_events

# Minimal valid StreamEvent payload for tests.
_SESSION_ID = "s1"
_CONTENT_EVENT = f'{{"chunk":"hi","session_id":"{_SESSION_ID}","type":"content"}}'
_TOOL_CALL_EVENT = (
    f'{{"tool_name":"search_flights","tool_args":{{}},"session_id":"{_SESSION_ID}","type":"tool_call"}}'
)


def test_parse_single_data_event_from_str() -> None:
    """Single data: line in a str produces a list of length 1 with correct fields."""
    # Arrange
    text = f"data: {_CONTENT_EVENT}\n\n"

    # Act
    events = parse_sse_events(text)

    # Assert
    assert len(events) == 1
    assert events[0].type == "content"
    assert events[0].session_id == _SESSION_ID


def test_parse_multiple_data_events_from_str() -> None:
    """Two data: blocks in a str produce a list of length 2."""
    # Arrange
    text = f"data: {_CONTENT_EVENT}\n\ndata: {_TOOL_CALL_EVENT}\n\n"

    # Act
    events = parse_sse_events(text)

    # Assert
    assert len(events) == 2


def test_parse_accepts_list_of_lines() -> None:
    """parse_sse_events accepts a list[str] of already-split lines."""
    # Arrange
    lines = [
        f"data: {_CONTENT_EVENT}",
        "",
        f"data: {_TOOL_CALL_EVENT}",
        ": keepalive",
    ]

    # Act
    events = parse_sse_events(lines)

    # Assert
    assert len(events) == 2


def test_parse_skips_blank_lines() -> None:
    """Blank and whitespace-only lines between data blocks are skipped."""
    # Arrange
    text = f"\n\ndata: {_CONTENT_EVENT}\n\n\n"

    # Act
    events = parse_sse_events(text)

    # Assert
    assert len(events) == 1


def test_parse_skips_keepalive_comments() -> None:
    """Lines starting with ':' (SSE keep-alive comments) are skipped."""
    # Arrange
    lines = [
        ": ping",
        f"data: {_CONTENT_EVENT}",
        ": keepalive",
    ]

    # Act
    events = parse_sse_events(lines)

    # Assert
    assert len(events) == 1


def test_parse_returns_list_of_streamevent_instances() -> None:
    """Each element in the returned list is a concrete event model, not a raw dict."""
    # Arrange
    text = f"data: {_CONTENT_EVENT}\n"

    # Act
    events = parse_sse_events(text)

    # Assert
    assert len(events) == 1
    assert isinstance(events[0], ContentEvent)


def test_parse_empty_string_returns_empty_list() -> None:
    """An empty input string returns an empty list."""
    # Act
    events = parse_sse_events("")

    # Assert
    assert events == []


def test_parse_malformed_json_raises_jsondecodeerror() -> None:
    """A data: line with invalid JSON raises json.JSONDecodeError."""
    # Arrange
    text = "data: not-json\n"

    # Act / Assert
    with pytest.raises(json.JSONDecodeError):
        parse_sse_events(text)


def test_parse_pydantic_validation_error_propagates() -> None:
    """A data: line with valid JSON but invalid StreamEvent fields raises ValidationError."""
    # Arrange — "INVALID_TYPE" is not in any discriminated union member's type literal
    text = f'data: {{"type": "INVALID_TYPE", "session_id": "{_SESSION_ID}"}}\n'

    # Act / Assert
    with pytest.raises(ValidationError):
        parse_sse_events(text)
