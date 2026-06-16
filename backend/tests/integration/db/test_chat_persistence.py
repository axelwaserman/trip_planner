"""Integration test: chat-turn persistence survives a ChatService restart.

Plan 06-04 success criterion: a chat turn run against a fresh
:class:`ChatService` writes its messages to Postgres via
:class:`PostgresMessageStore`; after the service is discarded and a new
:class:`ChatService` is constructed against the SAME database, the prior
turn's messages replay through ``await store.load(conversation_id)``.

Per-turn ``_metadata`` (provider/model/last_tool_invocation) lives in
process memory on the running ChatService — Plan 06-05a will surface
provider/model from the SQL ``conversation`` row so the second service
can fully resume an in-flight session. Until that lands, this test
asserts only that the message bytes round-trip through the DB; the
``ChatService`` rebuild is constructed against a fresh metadata dict
(intentional — the durability claim is independent of the metadata
projection).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.repository import _password_hasher
from app.chat import ChatService
from app.chat.repository import PostgresConversationRepository
from app.chat.store import PostgresMessageStore
from app.db.models import User
from app.llm.factory import LLMProviderFactory
from app.tools.flight_client import MockFlightAPIClient
from tests.fixtures.llm import MockLLMStream, _MockLLMProvider, default_session_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(database_url: str) -> None:
    """Apply alembic head against the per-test database."""
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(  # noqa: S603 — trusted args, no shell
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def sessionmaker(pg_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Build an ``async_sessionmaker`` against the per-test database with schema applied."""
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


def _build_chat_service(sessionmaker: async_sessionmaker[AsyncSession]) -> ChatService:
    """Build a :class:`ChatService` wired to Postgres + a deterministic mock LLM."""
    flight_client = MockFlightAPIClient(seed=42)
    provider = _MockLLMProvider(MockLLMStream.greeting())
    factory = MagicMock(spec=LLMProviderFactory)
    factory.build = MagicMock(return_value=provider)
    return ChatService(
        flight_client=flight_client,
        factory=factory,
        message_store=PostgresMessageStore(sessionmaker),
        conversation_repo=PostgresConversationRepository(sessionmaker),
    )


async def test_chat_turn_persists_and_replays_after_restart(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Run one chat turn → discard service → rebuild → message bytes still load."""
    # Arrange — seed a User + Conversation rows so the FK chain is satisfied,
    # then construct a ChatService bound to that user.
    async with sessionmaker() as session:
        user = User(
            username="chat-persistence-user",
            hashed_password=_password_hasher.hash("pw"),
            disabled=False,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    service_v1 = _build_chat_service(sessionmaker)

    # Create a conversation row + register session metadata. The ChatService
    # needs both a Postgres conversation row (FK target for the messages
    # table) and an in-process _metadata entry (so chat_stream can look up
    # the user_id). create_session() handles _metadata; the SQL conversation
    # row is provisioned via the ConversationRepository directly.
    conversation_id, probe_error = await service_v1.create_session(
        default_session_config(),
        user_id="chat-persistence-user",
    )
    assert probe_error is None

    conversation_uuid = UUID(conversation_id)
    # The conversation row needs to exist before chat_stream's append step;
    # Plan 06-05a will move this provisioning into create_session itself.
    # Insert a Conversation row whose id matches the conversation_id so the FK on
    # the message rows lines up.
    async with sessionmaker() as s:
        from app.db.models import Conversation  # noqa: PLC0415

        s.add(Conversation(id=conversation_uuid, user_id=user_id, provider="ollama", model="qwen3:4b"))
        await s.commit()

    # Act 1 — drive a real chat turn through the v1 service
    events_v1 = [e async for e in service_v1.chat_stream("hi", conversation_id)]

    # The greeting scenario produces only Content events; assert the stream
    # produced at least one (i.e. the run actually completed).
    content_events = [e for e in events_v1 if e.type == "content"]
    assert content_events, f"expected at least one ContentEvent, got: {[e.type for e in events_v1]}"

    # Discard service_v1 — simulate a backend restart. Do NOT call cleanup;
    # the durability claim is "messages survive even without a clean shutdown".
    del service_v1

    # Act 2 — fresh ChatService against the same DB, no _metadata seeding
    service_v2 = _build_chat_service(sessionmaker)
    replayed = await service_v2._message_store.load(conversation_uuid)

    # Assert — at minimum, the user's request and the assistant's response
    # round-tripped through the JSONB column.
    assert len(replayed) >= 2
    user_prompts = [
        part.content
        for msg in replayed
        if isinstance(msg, ModelRequest)
        for part in msg.parts
        if isinstance(part, UserPromptPart)
    ]
    assert "hi" in user_prompts
