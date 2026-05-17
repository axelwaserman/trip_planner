"""Unit tests for ChatService session management."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.chat import ChatService
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.llm.protocol import BoundProvider, LLMProvider
from app.tools.flight_client import FlightAPIClient


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
        session_id, _ = await service.create_session(_default_config())

        history = service.get_session_history(session_id)

        assert history is service._histories[session_id]

    def test_raises_value_error_for_unknown_session(self) -> None:
        service = make_service()

        with pytest.raises(ValueError, match="Session nonexistent not found"):
            service.get_session_history("nonexistent")

    async def test_updates_last_activity_on_access(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config())
        service._last_activity[session_id] = 0.0

        service.get_session_history(session_id)

        assert service._last_activity[session_id] > 0.0


class TestCreateSession:
    async def test_returns_uuid_string(self) -> None:
        service = make_service()
        session_id, error = await service.create_session(_default_config())

        assert error is None
        assert isinstance(session_id, str)
        assert len(session_id) == 36

    async def test_stores_metadata(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(
            _default_config(provider="openai", model="gpt-4o")
        )

        meta = service._metadata[session_id]
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4o"

    async def test_stores_bound_provider(self) -> None:
        """create_session must stash the BoundProvider for chat_stream to use."""
        service = make_service()
        session_id, _ = await service.create_session(_default_config())

        assert session_id in service._bound_providers


class TestCleanupExpiredSessions:
    async def test_removes_expired_session_from_all_dicts(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config())
        service._last_activity[session_id] = time.time() - 7200  # 2 hours ago

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 1
        assert session_id not in service._histories
        assert session_id not in service._metadata
        assert session_id not in service._bound_providers
        assert session_id not in service._last_activity

    async def test_leaves_active_sessions(self) -> None:
        service = make_service()
        session_id, _ = await service.create_session(_default_config())

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 0
        assert session_id in service._metadata

    async def test_returns_count_of_removed_sessions(self) -> None:
        service = make_service()
        ids: list[str] = []
        for _ in range(3):
            sid, _ = await service.create_session(_default_config())
            ids.append(sid)
        for sid in ids[:2]:
            service._last_activity[sid] = time.time() - 9999

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 2
