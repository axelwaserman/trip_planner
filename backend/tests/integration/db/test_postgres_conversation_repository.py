"""Integration tests for :class:`PostgresConversationRepository` (Plan 06-03 Task 3).

Locks the SQL contract:

- ``create`` persists the row with the right user_id/provider/model.
- ``list_for_user`` filters AND sorts by ``last_activity_at desc``.
- ``bump_last_activity`` advances the timestamp at the SQL layer.
- ``delete`` cascades to child ``message`` rows (V4 Access Control via the
  FK ON DELETE CASCADE from Plan 06-02).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.chat.repository import PostgresConversationRepository
from app.chat.store import PostgresMessageStore
from app.db.models import User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(database_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(  # noqa: S603 — trusted args; no shell
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def sessionmaker(pg_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    _run_alembic_upgrade(pg_database_url)
    engine = create_async_engine(pg_database_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_user(sessionmaker: async_sessionmaker[AsyncSession]) -> UUID:
    """Insert a User row and return its id (the FK target for ``conversation``)."""
    async with sessionmaker() as session:
        user = User(username=f"u-{uuid4().hex[:8]}", hashed_password="x", disabled=False)
        session.add(user)
        await session.commit()
        return user.id


async def test_create_persists_user_id_provider_model(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """create returns a UUID and persists the right user_id/provider/model."""
    # Arrange
    repo = PostgresConversationRepository(sessionmaker)
    user_id = await _seed_user(sessionmaker)

    # Act
    conversation_id = await repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")

    # Assert
    record = await repo.get(conversation_id)
    assert record is not None
    assert record.id == conversation_id
    assert record.user_id == user_id
    assert record.provider == "ollama"
    assert record.model == "qwen3:4b"


async def test_list_for_user_returns_only_users_conversations_sorted_by_last_activity_desc(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """list_for_user filters by user_id AND sorts by last_activity_at desc."""
    # Arrange — three convos for user A, one for user B
    repo = PostgresConversationRepository(sessionmaker)
    user_a = await _seed_user(sessionmaker)
    user_b = await _seed_user(sessionmaker)
    a1 = await repo.create(user_id=user_a, provider="ollama", model="qwen3:4b")
    a2 = await repo.create(user_id=user_a, provider="ollama", model="qwen3:8b")
    a3 = await repo.create(user_id=user_a, provider="openai", model="gpt-4o-mini")
    _b1 = await repo.create(user_id=user_b, provider="anthropic", model="claude-3-5-sonnet-20241022")

    # Force a known sort order via direct SQL on last_activity_at.
    async with sessionmaker() as session:
        await session.execute(
            text(
                "UPDATE conversation SET last_activity_at = :ts WHERE id = :id",
            ),
            [
                {"ts": "2026-06-01 00:00:00+00", "id": a1},
                {"ts": "2026-06-03 00:00:00+00", "id": a2},
                {"ts": "2026-06-02 00:00:00+00", "id": a3},
            ],
        )
        await session.commit()

    # Act
    results = await repo.list_for_user(user_a)

    # Assert
    assert len(results) == 3
    assert [r.id for r in results] == [a2, a3, a1]
    assert all(r.user_id == user_a for r in results)


async def test_bump_last_activity_advances_timestamp(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """bump_last_activity issues a SQL UPDATE that advances the column."""
    # Arrange
    repo = PostgresConversationRepository(sessionmaker)
    user_id = await _seed_user(sessionmaker)
    conversation_id = await repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")

    record_before = await repo.get(conversation_id)
    assert record_before is not None
    ts1 = record_before.last_activity_at

    # Sleep a hair so the new timestamp is observably later.
    await asyncio.sleep(0.02)

    # Act
    await repo.bump_last_activity(conversation_id)

    # Assert — read the column back via direct SQL
    async with sessionmaker() as session:
        result = await session.execute(
            text("SELECT last_activity_at FROM conversation WHERE id = :id"),
            {"id": conversation_id},
        )
        ts2 = result.scalar_one()
    assert ts2 > ts1


async def test_delete_cascades_to_messages(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """delete on a conversation cascades to its message rows (V4 Access Control)."""
    # Arrange
    conv_repo = PostgresConversationRepository(sessionmaker)
    msg_store = PostgresMessageStore(sessionmaker)
    user_id = await _seed_user(sessionmaker)
    conversation_id = await conv_repo.create(user_id=user_id, provider="ollama", model="qwen3:4b")

    # Append 3 messages so the cascade has rows to drop.
    await msg_store.append(
        conversation_id,
        [
            ModelRequest(parts=[UserPromptPart(content="m1")]),
            ModelRequest(parts=[UserPromptPart(content="m2")]),
            ModelRequest(parts=[UserPromptPart(content="m3")]),
        ],
    )
    async with sessionmaker() as session:
        result = await session.execute(
            text("SELECT count(*) FROM message WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
        assert result.scalar_one() == 3

    # Act — delete the conversation row
    await conv_repo.delete(conversation_id)

    # Assert — child messages are gone (FK ON DELETE CASCADE from Plan 06-02)
    async with sessionmaker() as session:
        result = await session.execute(
            text("SELECT count(*) FROM message WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
        assert result.scalar_one() == 0
    # And the conversation row itself is gone too.
    assert await conv_repo.get(conversation_id) is None
