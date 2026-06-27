"""Shared pytest fixtures for tests."""

import pytest

from app.auth.routes import create_access_token
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
