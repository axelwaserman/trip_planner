"""Unit tests for ChatService.chat_stream() with deterministic MockLLM."""

from unittest.mock import AsyncMock, patch

from app.chat.models import ErrorCode, ErrorEvent
from app.exceptions import APIError
from app.tools.flight_search import search_flights
from tests.fixtures.llm import (
    MockLLMStream,
    ToolCall,
    default_session_config,
    make_chat_service_with_mock_llm,
)


async def test_chat_stream_emits_content_events_for_greeting() -> None:
    """Content-only mock stream produces only 'content' type events and correct history."""
    # Arrange
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    # Act
    events = [e async for e in service.chat_stream("Hello", session_id)]

    # Assert
    content_events = [e for e in events if e.type == "content"]
    non_content_events = [e for e in events if e.type not in ("content",)]
    assert len(content_events) >= 1
    assert len(non_content_events) == 0

    history = service.get_session_history(session_id)
    msgs = list(history.messages)
    assert len(msgs) == 2


async def test_chat_stream_yields_error_event_on_tool_apierror() -> None:
    """chat_stream yields ErrorEvent(error_code=tool_error, retryable=True) when the tool raises APIError(retryable=True).

    Arrange: single-tool-call stream; mock search_flights.ainvoke to raise an APIError
    with retryable=True. Assert the last event is an ErrorEvent with the expected fields.

    NOTE: StructuredTool (Pydantic model) forbids attribute patching via setattr, so we
    patch at the class level: patch.object(type(search_flights), 'ainvoke', ...).
    """
    # Arrange
    service = make_chat_service_with_mock_llm(
        MockLLMStream.from_chunks(
            [
                [
                    ToolCall(
                        name="search_flights",
                        args={"origin": "LAX", "destination": "JFK", "departure_date": "2026-06-15", "passengers": 1},
                        id="call_test",
                    )
                ],
            ]
        )
    )
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    # Act — patch the tool's ainvoke at the class level to raise a retryable APIError
    with patch.object(
        type(search_flights),
        "ainvoke",
        new_callable=AsyncMock,
        side_effect=APIError(message="upstream boom", retryable=True),
    ):
        events = [e async for e in service.chat_stream("find flights", session_id)]

    # Assert — last event is an ErrorEvent with tool_error code and retryable=True
    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1
    err = error_events[0]
    assert isinstance(err, ErrorEvent)
    assert err.error_code == ErrorCode.tool_error
    assert err.retryable is True
    assert err.tool_name == "search_flights"
    assert err.raw_detail is not None
    assert "upstream boom" in (err.raw_detail or "")


async def test_chat_stream_yields_error_event_on_tool_unexpected_exception() -> None:
    """chat_stream yields ErrorEvent(retryable=False) when the tool raises a plain Exception.

    Arrange: single-tool-call stream; mock search_flights.ainvoke to raise a plain Exception.
    Assert the error event has retryable=False (non-APIError path).
    """
    # Arrange
    service = make_chat_service_with_mock_llm(
        MockLLMStream.from_chunks(
            [
                [
                    ToolCall(
                        name="search_flights",
                        args={"origin": "LAX", "destination": "JFK", "departure_date": "2026-06-15", "passengers": 1},
                        id="call_test",
                    )
                ],
            ]
        )
    )
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    # Act — patch the tool's ainvoke at the class level to raise a generic Exception
    with patch.object(
        type(search_flights),
        "ainvoke",
        new_callable=AsyncMock,
        side_effect=Exception("kaboom"),
    ):
        events = [e async for e in service.chat_stream("find flights", session_id)]

    # Assert — ErrorEvent with retryable=False on the non-APIError path
    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1
    err = error_events[0]
    assert isinstance(err, ErrorEvent)
    assert err.error_code == ErrorCode.tool_error
    assert err.retryable is False
    assert err.tool_name == "search_flights"


async def test_chat_stream_scrubs_api_key_from_raw_detail() -> None:
    """chat_stream scrubs API key patterns from ErrorEvent.raw_detail.

    Arrange: mock search_flights to raise APIError whose message contains a
    fake API key (``sk-AAAAAA...``). Assert the ErrorEvent.raw_detail does NOT
    contain the original key — the _scrub() function must have redacted it.
    """
    # Arrange
    fake_key = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"
    service = make_chat_service_with_mock_llm(
        MockLLMStream.from_chunks(
            [
                [
                    ToolCall(
                        name="search_flights",
                        args={"origin": "LAX", "destination": "JFK", "departure_date": "2026-06-15", "passengers": 1},
                        id="call_test",
                    )
                ],
            ]
        )
    )
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    # Act — patch the tool's ainvoke at the class level to raise an APIError with a key-like substring
    with patch.object(
        type(search_flights),
        "ainvoke",
        new_callable=AsyncMock,
        side_effect=APIError(message=f"call to OpenAI failed: {fake_key}", retryable=False),
    ):
        events = [e async for e in service.chat_stream("find flights", session_id)]

    # Assert — the key must be redacted from raw_detail
    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1
    err = error_events[0]
    assert err.raw_detail is not None
    assert fake_key not in (err.raw_detail or "")
    assert "sk-[REDACTED]" in (err.raw_detail or "")
