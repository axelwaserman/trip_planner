"""Unit tests for ChatService.chat_stream() with deterministic MockLLM."""

from tests.fixtures.llm import (
    MockLLMStream,
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
