"""Base API client abstract class."""

from abc import ABC, abstractmethod


class BaseAPIClient(ABC):
    """Abstract base class for external API clients.

    Provides common interface for all API clients in the application.
    Useful for multi-service APIs (e.g., Amadeus, Skyscanner, Expedia).
    """

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if API is available and responding.

        Returns:
            True if API is healthy and accessible, False otherwise

        Note:
            Implementations should catch exceptions and return False
            rather than raising, to allow graceful degradation.
        """
        ...
