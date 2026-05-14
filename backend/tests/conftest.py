"""Shared pytest fixtures for tests."""

from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from app.api.routes.auth import create_access_token
from app.tools.flight_client import MockFlightAPIClient


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return HTTP headers with a valid JWT Bearer token for the default admin user.

    Uses the ``admin`` user that is always present in the default AUTH_USERS store.
    """
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_flight_client() -> MockFlightAPIClient:
    """Create MockFlightAPIClient for testing.

    Returns:
        MockFlightAPIClient with fixed seed for reproducibility
    """
    return MockFlightAPIClient(seed=42)


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
