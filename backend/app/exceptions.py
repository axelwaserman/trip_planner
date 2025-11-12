"""Exception hierarchy for Trip Planner application."""


class TripPlannerError(Exception):
    """Base exception for trip planner."""


class APIError(TripPlannerError):
    """Base API error with retry capability flag."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        """Initialize API error.

        Args:
            message: Error message
            retryable: Whether this error should trigger a retry
        """
        super().__init__(message)
        self.retryable = retryable


class APITimeoutError(APIError):
    """Request timeout error - retryable."""

    def __init__(self, message: str) -> None:
        """Initialize timeout error.

        Args:
            message: Error message
        """
        super().__init__(message, retryable=True)


class APIRateLimitError(APIError):
    """Rate limit exceeded error - retryable with backoff."""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        """Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
        """
        super().__init__(message, retryable=True)
        self.retry_after = retry_after


class APIServerError(APIError):
    """Server error (5xx) - retryable."""

    def __init__(self, message: str) -> None:
        """Initialize server error.

        Args:
            message: Error message
        """
        super().__init__(message, retryable=True)


class APIClientError(APIError):
    """Client error (4xx) - not retryable."""

    def __init__(self, message: str) -> None:
        """Initialize client error.

        Args:
            message: Error message
        """
        super().__init__(message, retryable=False)


class FlightSearchError(TripPlannerError):
    """Flight search specific error."""
