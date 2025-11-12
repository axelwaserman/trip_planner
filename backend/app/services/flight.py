"""Flight search service with business logic."""

from decimal import Decimal
from typing import Literal

from app.domain.models import Flight, FlightQuery
from app.infrastructure.clients.flight import FlightAPIClient

SortBy = Literal["price", "duration", "departure"]


class FlightService:
    """Service for flight search with business logic.

    Handles sorting, filtering, and pagination of flight results.
    Delegates actual API calls to FlightAPIClient implementation.
    """

    def __init__(self, client: FlightAPIClient) -> None:
        """Initialize service with flight API client.

        Args:
            client: Flight API client implementation (mock or real)
        """
        self.client = client

    async def search_flights(
        self,
        query: FlightQuery,
        sort_by: SortBy = "price",
        max_price: Decimal | None = None,
        max_duration: int | None = None,
        max_stops: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Flight]:
        """Search for flights with business logic applied.

        Args:
            query: Flight search parameters
            sort_by: Sort criteria (price, duration, or departure time)
            max_price: Maximum price filter (inclusive)
            max_duration: Maximum duration in minutes (inclusive)
            max_stops: Maximum number of stops (inclusive)
            limit: Maximum number of results to return
            offset: Number of results to skip (for pagination)

        Returns:
            List of flights matching criteria, sorted and paginated
        """
        # Get flights from API client
        flights = await self.client.search(query)

        # Apply filters
        flights = self._apply_filters(
            flights,
            max_price=max_price,
            max_duration=max_duration,
            max_stops=max_stops,
        )

        # Apply sorting
        flights = self._sort_flights(flights, sort_by)

        # Apply pagination
        flights = self._paginate(flights, limit=limit, offset=offset)

        return flights

    async def get_flight_details(self, flight_id: str) -> Flight:
        """Get detailed information for a specific flight.

        Args:
            flight_id: Unique flight identifier

        Returns:
            Detailed flight information

        Raises:
            FlightSearchError: If flight not found
        """
        return await self.client.get_flight_details(flight_id)

    async def check_availability(self, flight_id: str) -> bool:
        """Check if a flight is still available for booking.

        Args:
            flight_id: Unique flight identifier

        Returns:
            True if flight is available, False otherwise
        """
        return await self.client.check_availability(flight_id)

    def _apply_filters(
        self,
        flights: list[Flight],
        max_price: Decimal | None = None,
        max_duration: int | None = None,
        max_stops: int | None = None,
    ) -> list[Flight]:
        """Apply filters to flight list.

        Args:
            flights: List of flights to filter
            max_price: Maximum price filter
            max_duration: Maximum duration filter
            max_stops: Maximum stops filter

        Returns:
            Filtered list of flights
        """
        filtered = flights

        if max_price is not None:
            filtered = [f for f in filtered if f.price <= max_price]

        if max_duration is not None:
            filtered = [f for f in filtered if f.duration_minutes <= max_duration]

        if max_stops is not None:
            filtered = [f for f in filtered if f.stops <= max_stops]

        return filtered

    def _sort_flights(self, flights: list[Flight], sort_by: SortBy) -> list[Flight]:
        """Sort flights by specified criteria.

        Args:
            flights: List of flights to sort
            sort_by: Sort criteria (price, duration, or departure)

        Returns:
            Sorted list of flights
        """
        if sort_by == "price":
            return sorted(flights, key=lambda f: f.price)
        elif sort_by == "duration":
            return sorted(flights, key=lambda f: f.duration_minutes)
        elif sort_by == "departure":
            return sorted(flights, key=lambda f: f.departure)
        return flights

    def _paginate(self, flights: list[Flight], limit: int, offset: int) -> list[Flight]:
        """Apply pagination to flight list.

        Args:
            flights: List of flights to paginate
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Paginated list of flights
        """
        return flights[offset : offset + limit]
