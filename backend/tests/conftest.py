"""Shared pytest fixtures for tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.language_models.chat_models import BaseChatModel

from app.infrastructure.storage.session import InMemorySessionStore
from app.services.flight import FlightService


@pytest.fixture
def mock_flight_service() -> AsyncMock:
    """Create mock FlightService for testing.

    Returns:
        AsyncMock FlightService with mock methods
    """
    return AsyncMock(spec=FlightService)


@pytest.fixture
async def session_store() -> InMemorySessionStore:
    """Create InMemorySessionStore for testing.

    Returns:
        Fresh InMemorySessionStore instance
    """
    return InMemorySessionStore(default_ttl_seconds=3600)


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create mock BaseChatModel for testing.

    Returns:
        MagicMock BaseChatModel with required methods
    """
    provider = MagicMock(spec=BaseChatModel)
    provider.model_name = "test-model"

    # Mock bind_tools to return self for method chaining
    provider.bind_tools.return_value = provider

    return provider
