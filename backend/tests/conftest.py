"""Shared pytest fixtures for tests."""

import pytest
from unittest.mock import AsyncMock

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
