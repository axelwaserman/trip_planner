"""Flight API client abstraction and implementations."""

import random
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.exceptions import FlightSearchError
from app.models import BookingClass, Flight, FlightQuery, SortBy


class FlightAPIClient(ABC):
    """Abstract base class for flight API clients.

    Provides interface for flight search operations.
    Concrete implementations handle specific APIs (Amadeus, mock, etc.).
    """

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if API is available.

        Returns:
            True if API is healthy, False otherwise
        """
        ...

    @abstractmethod
    async def search(
        self,
        query: FlightQuery,
        sort_by: SortBy = "price",
        max_price: Decimal | None = None,
        max_duration: int | None = None,
        max_stops: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Flight]:
        """Search for flights with filtering and sorting.

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
        """
        ...

    @abstractmethod
    async def check_availability(self, flight_id: str) -> bool:
        """Check if a flight is still available for booking.

        Args:
            flight_id: Unique flight identifier

        Returns:
            True if flight is available, False otherwise
        """
        ...


class MockFlightAPIClient(FlightAPIClient):
    """Mock flight API client for development and testing.

    Generates realistic but deterministic flight data for testing.
    No external API calls are made.
    """

    # Realistic carrier data
    CARRIERS = {
        "AA": "American Airlines",
        "DL": "Delta Air Lines",
        "UA": "United Airlines",
        "WN": "Southwest Airlines",
        "B6": "JetBlue Airways",
        "AS": "Alaska Airlines",
        "NK": "Spirit Airlines",
        "F9": "Frontier Airlines",
    }

    def __init__(self, seed: int | None = None) -> None:
        """Initialize mock client with optional random seed.

        Args:
            seed: Random seed for reproducible test data
        """
        self._rng = random.Random(seed)
        self._flight_cache: dict[str, Flight] = {}

    async def health_check(self) -> bool:
        """Mock API is always healthy."""
        return True

    async def search(
        self,
        query: FlightQuery,
        sort_by: SortBy = "price",
        max_price: Decimal | None = None,
        max_duration: int | None = None,
        max_stops: int | None = None,
        limit: int = 8,
        offset: int = 0,
    ) -> list[Flight]:
        """Generate mock flights with filtering and sorting applied.

        Args:
            query: Flight search parameters
            sort_by: Sort criteria (price, duration, or departure time)
            max_price: Maximum price filter (inclusive)
            max_duration: Maximum duration in minutes (inclusive)
            max_stops: Maximum number of stops (inclusive)
            limit: Maximum number of results to return (default 8)
            offset: Number of results to skip (for pagination)

        Returns:
            List of mock flights matching criteria, sorted and paginated
        """
        # Generate 3-8 flights for realistic results
        num_flights = self._rng.randint(max(3, limit), limit)
        flights = self._generate_flights(query, num_flights)

        # Apply filters
        flights = self._apply_filters(flights, max_price, max_duration, max_stops)

        # Apply sorting
        flights = self._sort_flights(flights, sort_by)

        # Apply pagination
        flights = flights[offset : offset + limit]

        # Cache for get_flight_details
        for flight in flights:
            self._flight_cache[flight.id] = flight

        return flights

    async def get_flight_details(self, flight_id: str) -> Flight:
        """Get cached flight details.

        Args:
            flight_id: Unique flight identifier

        Returns:
            Flight details

        Raises:
            FlightSearchError: If flight not found in cache
        """
        if flight_id not in self._flight_cache:
            raise FlightSearchError(f"Flight {flight_id} not found")
        return self._flight_cache[flight_id]

    async def check_availability(self, flight_id: str) -> bool:
        """Check mock flight availability.

        Args:
            flight_id: Flight identifier

        Returns:
            False if flight not in cache, otherwise 90% available
        """
        if flight_id not in self._flight_cache:
            return False
        return self._rng.random() < 0.9

    def _generate_flights(self, query: FlightQuery, count: int) -> list[Flight]:
        """Generate realistic mock flight data.

        Args:
            query: Flight query parameters
            count: Number of flights to generate

        Returns:
            List of generated flights
        """
        flights: list[Flight] = []

        for i in range(count):
            # Generate carrier and flight number
            carrier_code = self._rng.choice(list(self.CARRIERS.keys()))
            carrier_name = self.CARRIERS[carrier_code]
            flight_number = f"{carrier_code}{self._rng.randint(100, 9999)}"

            # Generate times (departure between 6 AM and 10 PM)
            departure_hour = self._rng.randint(6, 22)
            departure_minute = self._rng.choice([0, 15, 30, 45])
            departure = datetime.combine(
                query.departure_date,
                datetime.min.time().replace(hour=departure_hour, minute=departure_minute),
            ).replace(tzinfo=UTC)

            # Generate stops (favor direct flights)
            stops = self._rng.choices([0, 1, 2], weights=[60, 30, 10])[0]

            # Calculate distance-based duration
            # Rough distance estimation based on common routes
            distance_map = {
                ("LAX", "SFO"): 337,  # Short
                ("LAX", "JFK"): 2475,  # Long
                ("ORD", "DFW"): 802,   # Medium
                ("ORD", "ATL"): 606,   # Medium
                ("SFO", "SEA"): 680,   # Medium
                ("SFO", "LAX"): 337,   # Short
                ("JFK", "LAX"): 2475,  # Long
            }
            
            route_key = (query.origin, query.destination)
            reverse_route = (query.destination, query.origin)
            distance = distance_map.get(route_key) or distance_map.get(reverse_route, 1500)
            
            # Base duration: ~500 mph average speed + extra time for stops
            base_duration = int((distance / 500) * 60)
            variation = self._rng.randint(-20, 30)
            duration_minutes = base_duration + variation + (stops * 45)  # 45 min per stop
            arrival = departure + timedelta(minutes=duration_minutes)

            # Generate price (higher for direct flights, business class, etc.)
            base_price = self._rng.randint(200, 800)
            if stops == 0:
                base_price += 100
            price = Decimal(str(base_price))

            # Generate booking class (mostly economy)
            booking_class: BookingClass = self._rng.choices(
                ["economy", "premium_economy", "business", "first"],
                weights=[70, 15, 10, 5],
            )[0]

            if booking_class == "business":
                price *= Decimal("2.5")
            elif booking_class == "first":
                price *= Decimal("4.0")
            elif booking_class == "premium_economy":
                price *= Decimal("1.3")

            flight = Flight(
                id=str(uuid.uuid4()),
                origin=query.origin,
                destination=query.destination,
                departure=departure,
                arrival=arrival,
                price=price.quantize(Decimal("0.01")),
                currency="USD",
                carrier=carrier_name,
                flight_number=flight_number,
                duration_minutes=duration_minutes,
                stops=stops,
                booking_class=booking_class,
            )
            flights.append(flight)

        return flights

    def _apply_filters(
        self,
        flights: list[Flight],
        max_price: Decimal | None,
        max_duration: int | None,
        max_stops: int | None,
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
