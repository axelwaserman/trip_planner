"""Exception hierarchy for Trip Planner application."""

from dataclasses import dataclass


class TripPlannerError(Exception):
    """Base exception for trip planner."""


@dataclass
class APIError(TripPlannerError):
    """Base API error with retry capability flag."""

    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


@dataclass
class APITimeoutError(APIError):
    """Request timeout error - retryable."""

    retryable: bool = True


@dataclass
class APIRateLimitError(APIError):
    """Rate limit exceeded error - retryable with backoff."""

    retry_after: int = 60
    retryable: bool = True


@dataclass
class APIServerError(APIError):
    """Server error (5xx) - retryable."""

    retryable: bool = True


@dataclass
class APIClientError(APIError):
    """Client error (4xx) - not retryable."""

    retryable: bool = False


class FlightSearchError(TripPlannerError):
    """Flight search specific error."""
