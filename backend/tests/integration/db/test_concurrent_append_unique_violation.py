"""Pitfall 6 lock: PostgresMessageStore maps unique-violation to ConversationConcurrentAppendError.

The Phase 6 :class:`PostgresMessageStore` writes events under a non-atomic
``SELECT max(seq) … then INSERT`` pattern. Two writers reading the same
``max(seq)`` will both INSERT at ``current_max + 1`` and the
``(conversation_id, seq)`` unique index from Plan 06-02 rejects the second
commit with :class:`sqlalchemy.exc.IntegrityError`. The store MUST surface
that as a domain-level :class:`ConversationConcurrentAppendError` so the
caller (Plan 06-04 :class:`ChatService`) can emit a clear
:class:`app.chat.models.ErrorEvent` instead of letting raw SQL state reach
the SSE wire (T-06-03-04 / 06-RESEARCH.md Pitfall 6).

Wall-clock concurrency between two ``asyncio`` tasks on a fast local
Postgres is non-deterministic — the SELECT/INSERT/COMMIT triplet from one
task often finishes before the other reaches its SELECT, so neither sees
the same ``max(seq)`` and the unique index never fires. Instead of fighting
that, this test deterministically forces the race via a tiny subclass that
injects a saboteur INSERT between the production
:meth:`PostgresMessageStore.append` SELECT and COMMIT. The subclass shares
the production class's failure-mapping branch verbatim — what's actually
under test is the contract that ``IntegrityError → ConversationConcurrentAppendError``,
which is what Plan 06-04 will rely on.

Single-writer-per-conversation is the v1 invariant (Assumption A4); this
test locks the defensive path so the unique-violation can never be silently
lost.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_core import to_jsonable_python
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.chat.store import ConversationConcurrentAppendError, PostgresMessageStore
from app.db.models import Conversation, Message, User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage

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


async def _seed_user_and_conversation(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    async with sessionmaker() as session:
        user = User(username=f"u-{uuid4().hex[:8]}", hashed_password="x", disabled=False)
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, provider="ollama", model="qwen3:4b")
        session.add(conversation)
        await session.commit()
        return user.id, conversation.id


class _SaboteurMessageStore(PostgresMessageStore):
    """Test double that injects a saboteur INSERT between SELECT and COMMIT.

    Reproduces the deterministic shape of Pitfall 6: the saboteur opens a
    second session and INSERTs at the same ``seq`` the SUT computed, then
    commits. When the SUT then commits, the unique index rejects the
    duplicate. The :class:`IntegrityError` → :class:`ConversationConcurrentAppendError`
    mapping branch — copied verbatim from
    :meth:`PostgresMessageStore.append` — is what's under test.
    """

    async def append(self, conversation_id: UUID, messages: list[ModelMessage]) -> None:
        async with self._sessionmaker() as session:
            current_max_result = await session.execute(
                select(func.coalesce(func.max(col(Message.seq)), 0)).where(
                    col(Message.conversation_id) == conversation_id,
                ),
            )
            current_max = current_max_result.scalar_one()

            # Saboteur: INSERT at the same seq the SUT will claim, then commit.
            async with self._sessionmaker() as saboteur:
                await saboteur.execute(
                    text(
                        "INSERT INTO message (conversation_id, seq, payload) VALUES (:cid, :seq, '{}'::jsonb)",
                    ),
                    {"cid": conversation_id, "seq": current_max + 1},
                )
                await saboteur.commit()

            # SUT now adds the same seq → collision.
            for offset, msg in enumerate(messages, start=1):
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        seq=current_max + offset,
                        payload=to_jsonable_python(msg),
                    ),
                )
            try:
                await session.commit()
            except IntegrityError as exc:
                raise ConversationConcurrentAppendError(conversation_id) from exc


async def test_two_writers_race_on_seq_surfaces_concurrent_append_error(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Forced collision: SUT INSERTs at a seq another writer already committed → ConversationConcurrentAppendError."""
    # Arrange — empty conversation; the saboteur reserves seq=1, SUT claims it too.
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    racey = _SaboteurMessageStore(sessionmaker)

    # Act + Assert
    with pytest.raises(ConversationConcurrentAppendError) as excinfo:
        await racey.append(
            conversation_id,
            [ModelRequest(parts=[UserPromptPart(content="will collide on seq=1")])],
        )

    # The domain error carries the conversation_id; the underlying
    # IntegrityError is preserved as ``__cause__``.
    assert excinfo.value.conversation_id == conversation_id
    assert isinstance(excinfo.value.__cause__, IntegrityError)


async def test_production_append_does_not_collide_under_serial_calls(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Serial PostgresMessageStore.append calls produce monotonic seq with no error.

    Companion to the saboteur test: confirms the production
    :meth:`PostgresMessageStore.append` flow is correct under the
    single-writer-per-conversation invariant (Assumption A4) — the unique
    index does not fire when writers serialize naturally.
    """
    # Arrange
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    store = PostgresMessageStore(sessionmaker)

    # Act — three serial appends.
    for i in range(3):
        await store.append(
            conversation_id,
            [ModelRequest(parts=[UserPromptPart(content=f"msg-{i}")])],
        )

    # Assert — three rows, monotonic seq.
    async with sessionmaker() as session:
        result = await session.execute(
            text("SELECT seq FROM message WHERE conversation_id = :cid ORDER BY seq"),
            {"cid": conversation_id},
        )
        seqs = [row[0] for row in result]
    assert seqs == [1, 2, 3]
