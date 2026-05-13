"""Unit tests for ChatService session management."""

import time
from unittest.mock import MagicMock

import pytest

from app.chat import ChatService
from app.tools.flight_client import FlightAPIClient


def make_service() -> ChatService:
    """Return a ChatService with mock dependencies."""
    flight_client = MagicMock(spec=FlightAPIClient)
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    return ChatService(flight_client=flight_client, llm=llm)


class TestGetSessionHistory:
    def test_returns_history_for_existing_session(self) -> None:
        service = make_service()
        session_id = service.create_session()

        history = service.get_session_history(session_id)

        assert history is service._histories[session_id]

    def test_raises_value_error_for_unknown_session(self) -> None:
        service = make_service()

        with pytest.raises(ValueError, match="Session nonexistent not found"):
            service.get_session_history("nonexistent")

    def test_updates_last_activity_on_access(self) -> None:
        service = make_service()
        session_id = service.create_session()
        service._last_activity[session_id] = 0.0

        service.get_session_history(session_id)

        assert service._last_activity[session_id] > 0.0


class TestCreateSession:
    def test_returns_uuid_string(self) -> None:
        service = make_service()
        session_id = service.create_session()

        assert isinstance(session_id, str)
        assert len(session_id) == 36

    def test_stores_metadata(self) -> None:
        service = make_service()
        session_id = service.create_session(provider="openai", model="gpt-4o")

        meta = service._metadata[session_id]
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4o"

    def test_defaults_provider_and_model(self) -> None:
        service = make_service()
        session_id = service.create_session()

        meta = service._metadata[session_id]
        assert meta["provider"] == "ollama"
        assert meta["model"] == "qwen3:4b"


class TestCleanupExpiredSessions:
    def test_removes_expired_session_from_all_dicts(self) -> None:
        service = make_service()
        session_id = service.create_session()
        service._last_activity[session_id] = time.time() - 7200  # 2 hours ago

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 1
        assert session_id not in service._histories
        assert session_id not in service._metadata
        assert session_id not in service._last_activity

    def test_leaves_active_sessions(self) -> None:
        service = make_service()
        session_id = service.create_session()

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 0
        assert session_id in service._metadata

    def test_returns_count_of_removed_sessions(self) -> None:
        service = make_service()
        ids = [service.create_session() for _ in range(3)]
        for sid in ids[:2]:
            service._last_activity[sid] = time.time() - 9999

        removed = service.cleanup_expired_sessions(max_age_seconds=3600)

        assert removed == 2
