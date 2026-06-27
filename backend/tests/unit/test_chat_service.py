"""Unit tests for ChatService session lifecycle (Phase 5 / Plan 05-04 rewrite).

Phase 5 / Plan 05-04 (Wave 3): the Phase 4.5 file mocked ``BoundProvider``
and exercised the ``_bound_providers`` cache shape — both retired in this
plan. The rewritten file pivots onto the per-session ``_agents`` dict and
the ``ConversationStore`` seam, driving the rewritten
``make_chat_service_with_mock_llm`` fixture.
"""

import time

import pytest
from pydantic_ai import Agent

from app.chat.models import ErrorCode, ErrorEvent
from tests.fixtures.llm import (
    MockLLMStream,
    default_session_config,
    make_chat_service_with_mock_llm,
)


class TestCreateSession:
    async def test_returns_uuid_string(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, error = await service.create_session(default_session_config(), user_id="testuser")

        assert error is None
        assert isinstance(session_id, str)
        assert len(session_id) == 36  # canonical UUID length

    async def test_stores_metadata(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(
            default_session_config(provider="openai", model="gpt-4o"), user_id="testuser"
        )

        meta = service._metadata[session_id]
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
        session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        assert session_id in service._agents
        assert isinstance(service._agents[session_id], Agent)


class TestCleanupExpiredSessions:
    async def test_removes_expired_session_from_all_dicts(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(default_session_config(), user_id="testuser")
        service._last_activity[session_id] = time.time() - 7200  # 2 hours ago

        removed = await service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 1
        assert session_id not in service._metadata
        assert session_id not in service._agents
        assert session_id not in service._last_activity

    async def test_leaves_active_sessions(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        removed = await service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 0
        assert session_id in service._metadata

    async def test_returns_count_of_removed_sessions(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        ids: list[str] = []
        for _ in range(3):
            sid, _ = await service.create_session(default_session_config(), user_id="testuser")
            ids.append(sid)

        for sid in ids[:2]:
            service._last_activity[sid] = time.time() - 9999

        removed = await service.cleanup_expired_sessions(max_age_seconds=3600)

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

    async def test_delete_session_drops_agent(self) -> None:
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        assert session_id in service._agents
        await service.delete_session(session_id)

        assert session_id not in service._agents
        assert session_id not in service._metadata
        assert session_id not in service._last_activity


class TestConversationStorePersistence:
    """Persistence assertions: messages flow into the ConversationStore on success."""

    async def test_user_message_persisted_after_stream(self) -> None:
        """A successful turn appends both user and assistant messages to the store."""
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        msgs_before = await service._conversation_store.load(session_id)
        assert msgs_before == []

        _events = [e async for e in service.chat_stream("Plan a trip", session_id)]

        msgs_after = await service._conversation_store.load(session_id)
        assert len(msgs_after) >= 2  # at minimum: ModelRequest + ModelResponse

    async def test_persist_user_message_false_skips_append(self) -> None:
        """``persist_user_message=False`` does NOT append to the store (retry-prompt path)."""
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

        _events = [e async for e in service.chat_stream("synthetic retry", session_id, persist_user_message=False)]

        msgs = await service._conversation_store.load(session_id)
        assert msgs == []


class TestChatStreamTOCTOU:
    """C1: TOCTOU guard — session deleted between ownership check and generator start."""

    async def test_chat_stream_yields_session_error_for_unknown_session_id(self) -> None:
        """``chat_stream()`` with a never-created ``session_id`` must yield a
        ``session_error`` ErrorEvent and return rather than raising KeyError.

        Regression for C1 (Plan 05-07): the previous implementation did a bare
        ``self._metadata[session_id]["user_id"]`` which would raise ``KeyError``
        and produce an unhandled 500 for the route layer. The guard now yields
        a structured ``ErrorEvent`` instead.
        """
        # Arrange — service has no sessions; the id was never created
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        phantom_id = "00000000-0000-0000-0000-000000000000"

        # Act — collect all events; the generator must not raise
        events = [e async for e in service.chat_stream("hello", phantom_id)]

        # Assert — exactly one ErrorEvent with session_error code
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert events[0].error_code == ErrorCode.session_error
        assert events[0].retryable is False
        assert events[0].session_id == phantom_id

    async def test_chat_stream_yields_session_error_when_agent_missing_after_metadata(
        self,
    ) -> None:
        """TOCTOU edge: ``_metadata`` present but ``_agents`` missing (partial teardown).

        This is the "session_id in _metadata but deleted from _agents" race that
        could occur if another task deleted the agent between the ownership check and
        the stream start. The guard catches the ``KeyError`` from ``_agents`` too.
        """
        # Arrange — create session normally, then simulate partial teardown by
        # removing only the agent (not the metadata).
        service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
        session_id, _ = await service.create_session(default_session_config(), user_id="u")
        # Simulate partial teardown: agent gone but metadata still present
        del service._agents[session_id]

        # Act
        events = [e async for e in service.chat_stream("hello", session_id)]

        # Assert
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert events[0].error_code == ErrorCode.session_error


@pytest.mark.parametrize("max_age_seconds", [0, 3600])
async def test_cleanup_idempotent_when_called_twice(max_age_seconds: int) -> None:
    """Calling cleanup twice with the same threshold is safe (the store delete is no-op for unknowns)."""
    service = make_chat_service_with_mock_llm(MockLLMStream.greeting())
    session_id, _ = await service.create_session(default_session_config(), user_id="testuser")

    if max_age_seconds == 0:
        first = await service.cleanup_expired_sessions(max_age_seconds=0)
        second = await service.cleanup_expired_sessions(max_age_seconds=0)
        assert first == 1
        assert second == 0
    else:
        # Session is fresh; nothing should be cleaned up either time.
        assert await service.cleanup_expired_sessions(max_age_seconds=max_age_seconds) == 0
        assert await service.cleanup_expired_sessions(max_age_seconds=max_age_seconds) == 0
        assert session_id in service._metadata
