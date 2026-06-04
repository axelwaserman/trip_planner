"""Unit tests for :class:`InMemoryConversationRepository` (Plan 06-03 Task 3).

Locks the observable contract every :class:`ConversationRepository` impl must
satisfy:

- ``create`` returns a fresh UUID and persists a :class:`ConversationRecord`.
- ``get`` returns the record (or ``None`` for unknown ids).
- ``list_for_user`` filters by ``user_id`` AND sorts by ``last_activity_at`` desc.
- ``bump_last_activity`` advances the timestamp AND returns a new record
  reference (model_copy(update=...) — coding-style.md immutability rule).
- ``delete`` removes the conversation; ``get`` afterwards returns ``None``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from app.chat.repository import ConversationRecord, InMemoryConversationRepository

if TYPE_CHECKING:
    import pytest


async def test_create_returns_uuid_and_persists_record() -> None:
    """create generates a UUID and the record is retrievable via get."""
    # Arrange
    repo = InMemoryConversationRepository()
    user_id = uuid4()

    # Act
    conversation_id = await repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")

    # Assert
    assert isinstance(conversation_id, type(user_id))  # both UUIDs
    record = await repo.get(conversation_id)
    assert record is not None
    assert record.id == conversation_id
    assert record.user_id == user_id
    assert record.provider == "ollama"
    assert record.model == "qwen3:4b"


async def test_get_returns_conversation_record() -> None:
    """get returns the persisted ConversationRecord; None for unknowns."""
    # Arrange
    repo = InMemoryConversationRepository()
    user_id = uuid4()
    conversation_id = await repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")

    # Act
    found = await repo.get(conversation_id)
    not_found = await repo.get(uuid4())

    # Assert
    assert isinstance(found, ConversationRecord)
    assert found.id == conversation_id
    assert not_found is None


async def test_list_for_user_filters_and_sorts_by_last_activity_desc() -> None:
    """list_for_user returns only the user's conversations, sorted desc."""
    # Arrange — three convos for user A, one for user B
    repo = InMemoryConversationRepository()
    user_a = uuid4()
    user_b = uuid4()
    a1 = await repo.create(user_id=user_a, provider="ollama", model="qwen3:4b")
    a2 = await repo.create(user_id=user_a, provider="ollama", model="qwen3:8b")
    a3 = await repo.create(user_id=user_a, provider="openai", model="gpt-4o-mini")
    _b1 = await repo.create(user_id=user_b, provider="anthropic", model="claude-3-5-sonnet-20241022")

    # Manually rewrite last_activity_at so we can assert the sort order.
    # The repo stores ConversationRecord values; replace with an updated copy
    # so the immutable update path is exercised.
    now = datetime.now(UTC)
    repo._store[a1] = repo._store[a1].model_copy(update={"last_activity_at": now - timedelta(minutes=10)})
    repo._store[a2] = repo._store[a2].model_copy(update={"last_activity_at": now - timedelta(minutes=1)})
    repo._store[a3] = repo._store[a3].model_copy(update={"last_activity_at": now - timedelta(minutes=5)})

    # Act
    results = await repo.list_for_user(user_a)

    # Assert
    assert len(results) == 3
    assert [r.id for r in results] == [a2, a3, a1]  # most-recent first
    assert all(r.user_id == user_a for r in results)


async def test_bump_last_activity_updates_timestamp_immutably(monkeypatch: pytest.MonkeyPatch) -> None:
    """bump_last_activity advances the timestamp AND replaces the stored record reference."""
    # Arrange
    repo = InMemoryConversationRepository()
    user_id = uuid4()
    conversation_id = await repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")

    record_before = await repo.get(conversation_id)
    assert record_before is not None
    ts1 = record_before.last_activity_at

    # Monkeypatch datetime.now to force a strictly later timestamp than ts1
    # so the assertion is deterministic on fast runners (the in-memory test
    # otherwise sub-microsecond races with create()).
    later = ts1 + timedelta(milliseconds=10)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return later

    monkeypatch.setattr("app.chat.repository.datetime", _FakeDatetime)

    # Act
    await repo.bump_last_activity(conversation_id)

    # Assert
    record_after = await repo.get(conversation_id)
    assert record_after is not None
    assert record_after.last_activity_at > ts1
    # model_copy(update=...) returned a new object — ``is`` identity differs.
    assert record_after is not record_before


async def test_bump_last_activity_no_op_for_unknown() -> None:
    """bump_last_activity on an unknown id is a silent no-op (no raise)."""
    # Arrange
    repo = InMemoryConversationRepository()

    # Act + Assert — no raise
    await repo.bump_last_activity(uuid4())


async def test_delete_removes_conversation() -> None:
    """delete drops the record; subsequent get returns None."""
    # Arrange
    repo = InMemoryConversationRepository()
    user_id = uuid4()
    conversation_id = await repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")
    assert await repo.get(conversation_id) is not None

    # Act
    await repo.delete(conversation_id)

    # Assert
    assert await repo.get(conversation_id) is None


async def test_delete_no_op_for_unknown() -> None:
    """delete on an unknown id is a silent no-op (no raise)."""
    # Arrange
    repo = InMemoryConversationRepository()

    # Act + Assert — no raise
    await repo.delete(uuid4())
