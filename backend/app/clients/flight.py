"""Abstract flight API client interface."""

from abc import abstractmethod

from app.clients.base import BaseAPIClient
from app.models.flight import Flight, FlightQuery


class FlightAPIClient(BaseAPIClient):
    """Abstract flight API client interface.

    Defines the contract for all flight search implementations.
    Concrete implementations: MockFlightAPIClient, AmadeusFlightAPIClient.
    """

    @abstractmethod
    async def search(self, query: FlightQuery) -> list[Flight]:
        """Search for flights matching the query.

        Args:
            query: Flight search parameters including origin, destination, dates

        Returns:
            List of matching flights sorted by relevance

        Raises:
            FlightSearchError: If search fails due to business logic
            APIError: For API-related errors (timeout, rate limit, server error)
        """
        ...

    @abstractmethod
    async def get_flight_details(self, flight_id: str) -> Flight:
        """Get detailed information for a specific flight.

        Args:
            flight_id: Unique flight identifier

        Returns:
            Detailed flight information

        Raises:
            FlightSearchError: If flight not found
            APIError: For API-related errors
        """
        ...

    @abstractmethod
    async def check_availability(self, flight_id: str) -> bool:
        """Check if a flight is still available for booking.

        Args:
            flight_id: Unique flight identifier

        Returns:
            True if flight is available, False otherwise

        Raises:
            APIError: For API-related errors
        """
        ...
