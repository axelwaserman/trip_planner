"""Shared pytest fixtures for tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from app.auth.routes import create_access_token
from app.llm.base import LLMProvider
from app.llm.factory import LLMProviderFactory
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

    Legacy fixture retained for backwards compatibility with tests that
    haven't migrated to ``mock_llm_factory`` yet. Plan 09 deletes this fixture
    once all callers move over.

    Returns:
        MagicMock BaseChatModel with required methods
    """
    provider = MagicMock(spec=BaseChatModel)
    provider.model_name = "test-model"

    # Mock bind_tools to return self for method chaining
    provider.bind_tools.return_value = provider

    return provider


@pytest.fixture
def mock_llm_factory() -> MagicMock:
    """Create mock :class:`LLMProviderFactory` for ChatService tests.

    The mock factory's ``build()`` returns a mock :class:`LLMProvider` whose:

    - ``validate_config()`` returns ``None`` (probe success).
    - ``bind_tools()`` returns an unspec'd ``MagicMock`` standing in for the
      tool-bound runnable (the Phase 4.5 second-tier Protocol retired in
      plan 05-02 D-01..D-03; tests that need realistic ``astream`` behaviour
      attach their own mock).
    - ``get_provider_name()`` returns ``"ollama"``.
    - ``list_models()`` returns ``["qwen3:4b"]``.

    Tests that need realistic ``astream`` behaviour can attach their own mock
    via ``factory.build.return_value.bind_tools.return_value.astream = ...``.
    """
    bound = MagicMock()
    provider = MagicMock(spec=LLMProvider)
    provider.validate_config = AsyncMock(return_value=None)
    provider.bind_tools = MagicMock(return_value=bound)
    provider.get_provider_name = MagicMock(return_value="ollama")
    provider.list_models = AsyncMock(return_value=["qwen3:4b"])
    factory = MagicMock(spec=LLMProviderFactory)
    factory.build = MagicMock(return_value=provider)
    return factory
