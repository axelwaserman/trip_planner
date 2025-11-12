"""Tests for exception hierarchy."""

from app.exceptions import (
    APIClientError,
    APIError,
    APIRateLimitError,
    APIServerError,
    APITimeoutError,
    FlightSearchError,
    TripPlannerError,
)


def test_base_exception() -> None:
    """Test base TripPlannerError."""
    error = TripPlannerError("test error")
    assert str(error) == "test error"
    assert isinstance(error, Exception)


def test_api_error_not_retryable_by_default() -> None:
    """Test APIError is not retryable by default."""
    error = APIError(message="test error")
    assert error.retryable is False
    assert str(error) == "test error"


def test_api_error_custom_retryable() -> None:
    """Test APIError with custom retryable flag."""
    error = APIError(message="test error", retryable=True)
    assert error.retryable is True


def test_timeout_error_is_retryable() -> None:
    """Test APITimeoutError is retryable."""
    error = APITimeoutError(message="timeout")
    assert error.retryable is True
    assert str(error) == "timeout"


def test_rate_limit_error_is_retryable() -> None:
    """Test APIRateLimitError is retryable with retry_after."""
    error = APIRateLimitError(message="rate limited", retry_after=120)
    assert error.retryable is True
    assert error.retry_after == 120


def test_rate_limit_error_default_retry_after() -> None:
    """Test APIRateLimitError has default retry_after of 60."""
    error = APIRateLimitError(message="rate limited")
    assert error.retry_after == 60


def test_server_error_is_retryable() -> None:
    """Test APIServerError is retryable."""
    error = APIServerError(message="server error")
    assert error.retryable is True


def test_client_error_is_not_retryable() -> None:
    """Test APIClientError is not retryable."""
    error = APIClientError(message="bad request")
    assert error.retryable is False


def test_flight_search_error() -> None:
    """Test FlightSearchError is a TripPlannerError."""
    error = FlightSearchError("search failed")
    assert isinstance(error, TripPlannerError)
    assert str(error) == "search failed"
