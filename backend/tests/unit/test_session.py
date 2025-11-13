"""Tests for session domain model and storage."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.session import ChatSession
from app.infrastructure.storage.session import InMemorySessionStore


def test_chat_session_creation() -> None:
    """Test ChatSession is created with default values."""
    session = ChatSession(session_id="test-123")

    assert session.session_id == "test-123"
    assert session.message_count == 0
    assert session.metadata == {}
    assert isinstance(session.created_at, datetime)
    assert isinstance(session.last_activity, datetime)


def test_chat_session_touch() -> None:
    """Test touch() updates last_activity timestamp."""
    session = ChatSession(session_id="test-123")
    original_activity = session.last_activity

    # Wait a tiny bit and touch
    import time

    time.sleep(0.01)
    session.touch()

    assert session.last_activity > original_activity


def test_chat_session_increment_message_count() -> None:
    """Test increment_message_count() increases counter."""
    session = ChatSession(session_id="test-123")
    assert session.message_count == 0

    session.increment_message_count()
    assert session.message_count == 1

    session.increment_message_count()
    assert session.message_count == 2


def test_chat_session_is_expired() -> None:
    """Test is_expired() correctly identifies old sessions."""
    # Create session with old timestamp
    old_time = datetime.now(UTC) - timedelta(seconds=3700)  # > 1 hour ago
    session = ChatSession(session_id="test-123", last_activity=old_time)

    assert session.is_expired(max_age_seconds=3600) is True
    assert session.is_expired(max_age_seconds=7200) is False


def test_chat_session_metadata() -> None:
    """Test session metadata can store arbitrary data."""
    session = ChatSession(
        session_id="test-123",
        metadata={"llm_provider": "ollama", "llm_model": "qwen3:8b", "user_id": 42},
    )

    assert session.metadata["llm_provider"] == "ollama"
    assert session.metadata["llm_model"] == "qwen3:8b"
    assert session.metadata["user_id"] == 42


@pytest.mark.asyncio
async def test_in_memory_session_store_create() -> None:
    """Test InMemorySessionStore can create sessions."""
    store = InMemorySessionStore()

    session = await store.create_session()

    assert session.session_id is not None
    assert len(session.session_id) > 0
    assert store.get_session_count() == 1


@pytest.mark.asyncio
async def test_in_memory_session_store_get() -> None:
    """Test InMemorySessionStore can retrieve sessions."""
    store = InMemorySessionStore()

    created_session = await store.create_session()
    retrieved_session = await store.get_session(created_session.session_id)

    assert retrieved_session is not None
    assert retrieved_session.session_id == created_session.session_id


@pytest.mark.asyncio
async def test_in_memory_session_store_get_nonexistent() -> None:
    """Test InMemorySessionStore returns None for non-existent sessions."""
    store = InMemorySessionStore()

    session = await store.get_session("nonexistent-id")

    assert session is None


@pytest.mark.asyncio
async def test_in_memory_session_store_update() -> None:
    """Test InMemorySessionStore can update sessions."""
    store = InMemorySessionStore()

    session = await store.create_session()
    session.metadata["test_key"] = "test_value"
    await store.update_session(session)

    retrieved = await store.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.metadata["test_key"] == "test_value"


@pytest.mark.asyncio
async def test_in_memory_session_store_delete() -> None:
    """Test InMemorySessionStore can delete sessions."""
    store = InMemorySessionStore()

    session = await store.create_session()
    assert store.get_session_count() == 1

    deleted = await store.delete_session(session.session_id)
    assert deleted is True
    assert store.get_session_count() == 0

    # Second delete returns False
    deleted_again = await store.delete_session(session.session_id)
    assert deleted_again is False


@pytest.mark.asyncio
async def test_in_memory_session_store_get_history() -> None:
    """Test InMemorySessionStore provides chat history."""
    store = InMemorySessionStore()

    session = await store.create_session()
    history = await store.get_history(session.session_id)

    # History should be empty initially
    assert len(history.messages) == 0

    # Add message
    history.add_user_message("Hello!")
    assert len(history.messages) == 1

    # Retrieve again - should be same instance
    history2 = await store.get_history(session.session_id)
    assert len(history2.messages) == 1


@pytest.mark.asyncio
async def test_in_memory_session_store_cleanup_expired() -> None:
    """Test InMemorySessionStore cleans up expired sessions."""
    store = InMemorySessionStore(default_ttl_seconds=60)

    # Create recent session
    session1 = await store.create_session()

    # Create expired session
    session2 = await store.create_session()
    session2.last_activity = datetime.now(UTC) - timedelta(seconds=120)
    await store.update_session(session2)

    # Cleanup with 60 second max age
    cleaned_count = await store.cleanup_expired(max_age_seconds=60)

    assert cleaned_count == 1
    assert store.get_session_count() == 1

    # Only recent session should remain
    assert await store.get_session(session1.session_id) is not None
    assert await store.get_session(session2.session_id) is None


@pytest.mark.asyncio
async def test_in_memory_session_store_multiple_sessions() -> None:
    """Test InMemorySessionStore handles multiple independent sessions."""
    store = InMemorySessionStore()

    session1 = await store.create_session()
    session2 = await store.create_session()
    session3 = await store.create_session()

    assert store.get_session_count() == 3
    assert session1.session_id != session2.session_id
    assert session2.session_id != session3.session_id

    # Each should have independent history
    history1 = await store.get_history(session1.session_id)
    history2 = await store.get_history(session2.session_id)

    history1.add_user_message("Message in session 1")
    history2.add_user_message("Message in session 2")

    assert len(history1.messages) == 1
    assert len(history2.messages) == 1
    assert history1.messages[0].content != history2.messages[0].content
