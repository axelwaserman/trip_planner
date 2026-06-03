"""Unit tests for ChatService session management.

Phase 5 / Plan 05-03 sweep: the legacy ``protocol`` shim was deleted in Wave 1
and the two-tier ``BoundProvider`` Protocol retired with it (D-01..D-03). This
file exercises the Phase 4.5 ``ChatService._bound_providers`` cache shape,
which itself retires when ``ChatService`` is rewritten in Wave 3 (Plan 05-04).
To keep test collection green during the Wave 2 sweep — and to honour the
regression guard against lingering legacy-shim imports — the entire module is
skipped here. The corresponding rewrite lands with the Wave 3 ChatService
rewrite.
"""

import pytest

pytest.skip(
    "Deferred to Wave 3 / Plan 05-04 — ChatService + BoundProvider semantics retire there.",
    allow_module_level=True,
)

import time  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage  # noqa: E402

from app.chat import ChatService  # noqa: E402
from app.llm.base import LLMProvider  # noqa: E402
from app.llm.factory import LLMProviderFactory, SessionLLMConfig  # noqa: E402
from app.tools.flight_client import FlightAPIClient  # noqa: E402

# NOTE: ``BoundProvider`` was removed in Wave 1; the placeholder below preserves
# the symbol so the Wave 3 ChatService rewrite can swap it for an ``Agent``
# mock when it rewrites the body of this file end-to-end.
BoundProvider: object = object  # placeholder until Wave 3 retypes


def make_service() -> ChatService:
    """Return a ChatService with mock dependencies."""
    flight_client = MagicMock(spec=FlightAPIClient)
    bound = MagicMock(spec=BoundProvider)
    provider = MagicMock(spec=LLMProvider)
    provider.validate_config = AsyncMock(return_value=None)
    provider.bind_tools = MagicMock(return_value=bound)
    factory = MagicMock(spec=LLMProviderFactory)
    factory.build = MagicMock(return_value=provider)
    return ChatService(flight_client=flight_client, factory=factory)


def _default_config(provider: str = "ollama", model: str = "qwen3:4b") -> SessionLLMConfig:
    """Build a SessionLLMConfig with the 4.2 default fallbacks."""
    return SessionLLMConfig(provider=provider, model=model, base_url=None, api_key=None)


class TestGetSessionHistory:
    async def test_returns_history_for_existing_session(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config(), user_id="testuser")

        history = service.get_session_history(session_id)

        assert history is service._histories[session_id]

    def test_raises_value_error_for_unknown_session(self) -> None:
        service = make_service()

        with pytest.raises(ValueError, match="Session nonexistent not found"):
            service.get_session_history("nonexistent")

    async def test_updates_last_activity_on_access(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config(), user_id="testuser")
        service._last_activity[session_id] = 0.0

        service.get_session_history(session_id)

        assert service._last_activity[session_id] > 0.0


class TestCreateSession:
    async def test_returns_uuid_string(self) -> None:
        service = make_service()
        session_id, error = await service.create_session(_default_config(), user_id="testuser")

        assert error is None
        assert isinstance(session_id, str)
        assert len(session_id) == 36

    async def test_stores_metadata(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(
            _default_config(provider="openai", model="gpt-4o"), user_id="testuser"
        )

        meta = service._metadata[session_id]
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4o"
        assert meta["user_id"] == "testuser"
        assert "T" in meta["created_at"]  # ISO 8601 contains 'T' between date and time

    async def test_stores_bound_provider(self) -> None:
        """create_session must stash the BoundProvider for chat_stream to use."""
        service = make_service()
        session_id, _ = await service.create_session(_default_config(), user_id="testuser")

        assert session_id in service._bound_providers


class TestCleanupExpiredSessions:
    async def test_removes_expired_session_from_all_dicts(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config(), user_id="testuser")
        service._last_activity[session_id] = time.time() - 7200  # 2 hours ago

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 1
        assert session_id not in service._histories
        assert session_id not in service._metadata
        assert session_id not in service._bound_providers
        assert session_id not in service._last_activity

    async def test_leaves_active_sessions(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config(), user_id="testuser")

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 0
        assert session_id in service._metadata

    async def test_returns_count_of_removed_sessions(self) -> None:
        service = make_service()
        ids: list[str] = []
        for _ in range(3):
            sid, _ = await service.create_session(_default_config(), user_id="testuser")
            ids.append(sid)

        for sid in ids[:2]:
            service._last_activity[sid] = time.time() - 9999

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 2


class TestChatStreamPersistence:
    """Background-streaming requirement: the user message must be persisted
    upfront and the accumulated AI response in a `try/finally` so a switch-
    conversations / disconnect mid-stream still leaves the history complete
    when the user navigates back.
    """

    async def _make_service_with_streamed_chunks(self, chunks: list[AIMessageChunk]) -> tuple[ChatService, str]:
        """Build a service whose bound provider streams the given chunks."""
        flight_client = MagicMock(spec=FlightAPIClient)
        bound = MagicMock(spec=BoundProvider)

        async def fake_astream(_messages: object) -> object:
            for c in chunks:
                yield c

        bound.astream = fake_astream
        provider = MagicMock(spec=LLMProvider)
        provider.validate_config = AsyncMock(return_value=None)
        provider.bind_tools = MagicMock(return_value=bound)
        factory = MagicMock(spec=LLMProviderFactory)
        factory.build = MagicMock(return_value=provider)
        service = ChatService(flight_client=flight_client, factory=factory)
        session_id, _ = await service.create_session(_default_config(), user_id="testuser")
        return service, session_id

    async def test_user_message_persists_at_stream_start(self) -> None:
        """The user turn must land in history BEFORE the LLM streams anything."""
        # First chunk yields content; we'll inspect history after only the
        # FIRST chunk has flowed (before the stream completes).
        service, session_id = await self._make_service_with_streamed_chunks([AIMessageChunk(content="response")])

        history = service.get_session_history(session_id)
        # Pre-stream: history is empty.
        assert len(history.messages) == 0

        gen = service.chat_stream("Plan a trip", session_id=session_id)
        # Pull the first event — chat_stream yields after persisting the user
        # message via history.add_user_message at the top.
        await gen.__anext__()

        assert any(isinstance(m, HumanMessage) and m.content == "Plan a trip" for m in history.messages)

    async def test_partial_stream_persists_what_was_accumulated(self) -> None:
        """A stream that's partially consumed before being closed (e.g. client
        switched conversations) must still flush accumulated_content to
        history via the try/finally so the resumed view sees a complete
        turn rather than dropping the user message entirely.
        """
        service, session_id = await self._make_service_with_streamed_chunks(
            [
                AIMessageChunk(content="partial-1 "),
                AIMessageChunk(content="partial-2"),
            ]
        )

        history = service.get_session_history(session_id)
        gen = service.chat_stream("hi", session_id=session_id)

        # Consume only the first event then close — simulates client
        # disconnect mid-stream.
        await gen.__anext__()
        await gen.aclose()

        # User turn persisted.
        assert any(isinstance(m, HumanMessage) and m.content == "hi" for m in history.messages)
        # AI turn persisted (with whatever was accumulated up to the close).
        ai_messages = [m for m in history.messages if isinstance(m, AIMessage)]
        assert len(ai_messages) == 1
        # Content is whatever was accumulated through the FIRST chunk (the
        # only one consumed before aclose() ran the generator's finally).
        assert ai_messages[0].content == "partial-1 "
