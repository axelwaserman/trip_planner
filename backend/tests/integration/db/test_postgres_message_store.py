"""Integration tests for :class:`PostgresMessageStore` against a real DB.

Plan 06-03 Task 3: locks the JSONB round-trip, monotonic seq invariant, and
the Pitfall 5 oversize-payload guardrail.

Each test gets its own per-test database via the ``pg_database_url`` fixture
(Plan 06-02 ``conftest.py``), with the schema applied via ``alembic upgrade
head`` from a subprocess. The Postgres service is the compose ``db`` from
CONTEXT.md D-10; bringing it up is the precondition for every test in this
file (``just compose-up`` once Plan 06-06 lands).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.chat.store import PostgresMessageStore
from app.config import settings
from app.db.models import Conversation, User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# `backend/` — the directory that contains alembic.ini. ``cwd`` for every
# alembic subprocess.
_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(database_url: str) -> None:
    """Run ``uv run alembic upgrade head`` against ``database_url``."""
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
    """Build an ``async_sessionmaker`` against the per-test database.

    Runs ``alembic upgrade head`` to materialise the Phase 6 schema, then
    yields an ``async_sessionmaker`` callers can pass to
    :class:`PostgresMessageStore` / :class:`PostgresConversationRepository`.
    """
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
    """Insert a User + Conversation row and return ``(user_id, conversation_id)``.

    The ``message`` table FK requires a parent ``conversation`` row, which in
    turn requires a parent ``user`` row. Tests need both before exercising
    :class:`PostgresMessageStore`.
    """
    async with sessionmaker() as session:
        user = User(username=f"u-{uuid4().hex[:8]}", hashed_password="x", disabled=False)
        session.add(user)
        await session.flush()  # populate user.id (server default + Python uuid4)
        conversation = Conversation(user_id=user.id, provider="ollama", model="qwen3:4b")
        session.add(conversation)
        await session.commit()
        return user.id, conversation.id


async def test_append_then_load_roundtrips_modelmessages_via_jsonb(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """JSONB round-trip preserves UserPromptPart + TextPart on a mixed batch."""
    # Arrange
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    store = PostgresMessageStore(sessionmaker)
    user_msg = ModelRequest(parts=[UserPromptPart(content="find flights to LAX")])
    assistant_msg = ModelResponse(parts=[TextPart(content="Here are the options.")])

    # Act
    await store.append(conversation_id, [user_msg, assistant_msg])
    loaded = await store.load(conversation_id)

    # Assert
    assert len(loaded) == 2
    assert isinstance(loaded[0], ModelRequest)
    assert isinstance(loaded[0].parts[0], UserPromptPart)
    assert loaded[0].parts[0].content == "find flights to LAX"
    assert isinstance(loaded[1], ModelResponse)
    assert isinstance(loaded[1].parts[0], TextPart)
    assert loaded[1].parts[0].content == "Here are the options."


async def test_seq_is_monotonic_per_conversation(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Three batches of 2 messages produce seq = 1..6 on the same conversation."""
    # Arrange
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    store = PostgresMessageStore(sessionmaker)

    def _make_batch(prefix: str) -> list[ModelRequest | ModelResponse]:
        return [
            ModelRequest(parts=[UserPromptPart(content=f"{prefix}-user")]),
            ModelResponse(parts=[TextPart(content=f"{prefix}-assistant")]),
        ]

    # Act — three append calls, two messages each
    await store.append(conversation_id, _make_batch("a"))
    await store.append(conversation_id, _make_batch("b"))
    await store.append(conversation_id, _make_batch("c"))

    # Assert — direct SQL probes the seq column ordering
    async with sessionmaker() as session:
        result = await session.execute(
            text("SELECT seq FROM message WHERE conversation_id = :cid ORDER BY seq"),
            {"cid": conversation_id},
        )
        seqs = [row[0] for row in result]
    assert seqs == [1, 2, 3, 4, 5, 6]


async def test_first_user_message_preview_via_sql(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """preview returns first 80 chars of the earliest UserPromptPart."""
    # Arrange
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    store = PostgresMessageStore(sessionmaker)
    long_content = "find flights to LAX please " * 5  # ~135 chars
    msgs: list[ModelRequest | ModelResponse] = [
        ModelRequest(parts=[UserPromptPart(content=long_content)]),
        ModelResponse(parts=[TextPart(content="ok")]),
        ModelRequest(parts=[UserPromptPart(content="follow-up question")]),
        ModelResponse(parts=[TextPart(content="ok 2")]),
    ]
    await store.append(conversation_id, msgs)

    # Act
    preview = await store.first_user_message_preview(conversation_id)

    # Assert
    assert preview is not None
    assert preview == long_content[:80]
    assert len(preview) == 80


async def test_first_user_message_preview_returns_none_for_empty(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """preview returns ``None`` when the conversation carries no messages yet."""
    # Arrange
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    store = PostgresMessageStore(sessionmaker)

    # Act
    preview = await store.first_user_message_preview(conversation_id)

    # Assert
    assert preview is None


async def test_payload_size_guardrail_rejects_oversize_payload(
    monkeypatch: pytest.MonkeyPatch,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Pitfall 5 lock: append rejects payloads larger than the Settings cap."""
    # Arrange — drop the cap to a hard-to-miss value.
    monkeypatch.setattr(settings, "message_max_payload_bytes", 100)
    _, conversation_id = await _seed_user_and_conversation(sessionmaker)
    store = PostgresMessageStore(sessionmaker)
    huge = "x" * 400  # ~400 bytes serialized — well past the 100-byte cap
    huge_msg = ModelRequest(parts=[UserPromptPart(content=huge)])

    # Act + Assert
    with pytest.raises(ValueError, match="message_max_payload_bytes"):
        await store.append(conversation_id, [huge_msg])

    # AND: no row was actually inserted.
    async with sessionmaker() as session:
        result = await session.execute(
            text("SELECT count(*) FROM message WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
        count = result.scalar_one()
    assert count == 0
