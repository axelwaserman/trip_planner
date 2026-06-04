"""Unit tests for ChatService session lifecycle (Phase 6 / Plan 06-04 rewire).

Phase 6 / Plan 06-04: the Phase 5 single ``ConversationStore`` collaborator
split into ``MessageStore`` (events) + ``ConversationRepository`` (meta-CRUD).
History assertions migrate from ``service._conversation_store.load(...)`` to
``service._message_store.load(UUID(conversation_id))``.
"""

import time
from uuid import UUID

import pytest
from pydantic_ai import Agent

from tests.fixtures.llm import (
    MockLLMStream,
    default_session_config,
    make_chat_service_with_mock_llm,
)


class TestCreateSession:
    async def test_returns_uuid_string(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, error = await service.create_session(default_session_config(), user_id="testuser")

        assert error is None
        assert isinstance(conversation_id, str)
        assert len(conversation_id) == 36  # canonical UUID length

    async def test_stores_metadata(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(
            default_session_config(provider="openai", model="gpt-4o"), user_id="testuser"
        )

        meta = service._metadata[conversation_id]
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4o"
        assert meta["user_id"] == "testuser"
        assert "T" in meta["created_at"]  # ISO 8601 contains 'T' between date and time

    async def test_stores_pydantic_ai_agent(self) -> None:
        """create_session must stash a real ``pydantic_ai.Agent`` in ``_agents``.

        Replaces the Phase 4.5 ``test_stores_bound_provider`` — same intent
        (the agent is reused across turns), new collection (D-10).
        """
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        assert conversation_id in service._agents
        assert isinstance(service._agents[conversation_id], Agent)


class TestCleanupExpiredSessions:
    async def test_removes_expired_session_from_all_dicts(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")
        service._last_activity[conversation_id] = time.time() - 7200  # 2 hours ago

        removed = await service.cleanup_expired_conversations(max_age_seconds=3600)

        assert removed == 1
        assert conversation_id not in service._metadata
        assert conversation_id not in service._agents
        assert conversation_id not in service._last_activity

    async def test_leaves_active_sessions(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        removed = await service.cleanup_expired_conversations(max_age_seconds=3600)

        assert removed == 0
        assert conversation_id in service._metadata

    async def test_returns_count_of_removed_sessions(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        ids: list[str] = []
        for _ in range(3):
            sid, _ = await service.create_session(default_session_config(), user_id="testuser")
            ids.append(sid)

        for sid in ids[:2]:
            service._last_activity[sid] = time.time() - 9999

        removed = await service.cleanup_expired_conversations(max_age_seconds=3600)

        assert removed == 2


class TestAgentsLifecycle:
    """Per-session ``_agents`` dict lifecycle (D-10)."""

    async def test_each_session_gets_its_own_agent(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        sid_a, _ = await service.create_session(default_session_config(), user_id="alice")
        sid_b, _ = await service.create_session(default_session_config(), user_id="bob")

        assert sid_a != sid_b
        # Each session has its own Agent instance (the fixture's _MockLLMProvider
        # builds a new FunctionModel-backed Agent on every build_agent() call).
        assert service._agents[sid_a] is not service._agents[sid_b]

    async def test_delete_conversation_drops_agent(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        assert conversation_id in service._agents
        await service.delete_conversation(conversation_id)

        assert conversation_id not in service._agents
        assert conversation_id not in service._metadata
        assert conversation_id not in service._last_activity


class TestMessageStorePersistence:
    """Persistence assertions: messages flow into the MessageStore on success."""

    async def test_user_message_persisted_after_stream(self) -> None:
        """A successful turn appends both user and assistant messages to the store."""
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        msgs_before = await service._message_store.load(UUID(conversation_id))
        assert msgs_before == []

        _events = [e async for e in service.chat_stream("Plan a trip", conversation_id)]

        msgs_after = await service._message_store.load(UUID(conversation_id))
        assert len(msgs_after) >= 2  # at minimum: ModelRequest + ModelResponse

    async def test_persist_user_message_false_skips_append(self) -> None:
        """``persist_user_message=False`` does NOT append to the store (retry-prompt path)."""
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        _events = [e async for e in service.chat_stream("synthetic retry", conversation_id, persist_user_message=False)]

        msgs = await service._message_store.load(UUID(conversation_id))
        assert msgs == []


@pytest.mark.parametrize("max_age_seconds", [0, 3600])
async def test_cleanup_idempotent_when_called_twice(max_age_seconds: int) -> None:
    """Calling cleanup twice with the same threshold is safe (the store delete is no-op for unknowns)."""
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    conversation_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    if max_age_seconds == 0:
        first = await service.cleanup_expired_conversations(max_age_seconds=0)
        second = await service.cleanup_expired_conversations(max_age_seconds=0)
        assert first == 1
        assert second == 0
    else:
        # Session is fresh; nothing should be cleaned up either time.
        assert await service.cleanup_expired_conversations(max_age_seconds=max_age_seconds) == 0
        assert await service.cleanup_expired_conversations(max_age_seconds=max_age_seconds) == 0
        assert conversation_id in service._metadata
