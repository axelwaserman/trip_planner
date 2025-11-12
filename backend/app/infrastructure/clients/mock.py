"""Mock flight API client for development and testing."""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.models import Flight, FlightQuery
from app.infrastructure.clients.flight import FlightAPIClient

# Major airlines with typical flight number prefixes
AIRLINES = [
    ("American Airlines", "AA"),
    ("United Airlines", "UA"),
    ("Delta Air Lines", "DL"),
    ("Southwest Airlines", "WN"),
    ("JetBlue Airways", "B6"),
    ("Alaska Airlines", "AS"),
    ("Spirit Airlines", "NK"),
    ("Frontier Airlines", "F9"),
]

# Base prices per distance tier (in USD)
BASE_PRICES = {
    "short": (120, 300),  # < 1000 miles
    "medium": (250, 600),  # 1000-2500 miles
    "long": (400, 1200),  # > 2500 miles
}

# Price multipliers by booking class
CLASS_MULTIPLIERS = {
    "economy": 1.0,
    "premium_economy": 1.5,
    "business": 3.0,
    "first": 5.0,
}

# Approximate distances between major airports (in miles)
AIRPORT_DISTANCES = {
    ("LAX", "JFK"): 2475,
    ("LAX", "SFO"): 337,
    ("LAX", "SEA"): 954,
    ("LAX", "ORD"): 1745,
    ("JFK", "SFO"): 2586,
    ("JFK", "ORD"): 740,
    ("JFK", "MIA"): 1089,
    ("SFO", "SEA"): 679,
    ("ORD", "DFW"): 802,
    ("ORD", "ATL"): 606,
}


class MockFlightAPIClient(FlightAPIClient):
    """Mock flight API client returning realistic dummy data.

    Generates varied flight options with:
    - Different airlines and flight numbers
    - Realistic prices based on distance and booking class
    - Varied departure times throughout the day
    - Random layovers (0-2 stops)
    - Duration calculations based on distance and stops

    Useful for development and testing without external API calls.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Initialize mock client with optional random seed.

        Args:
            seed: Random seed for reproducible results (testing). None for random data.
        """
        if seed is not None:
            random.seed(seed)
        self._flights_cache: dict[str, Flight] = {}

    async def search(self, query: FlightQuery) -> list[Flight]:
        """Search for flights matching the query.

        Generates 3-8 realistic flight options with varied:
        - Airlines and prices
        - Departure times (morning, afternoon, evening)
        - Number of stops (0-2)
        - Duration based on distance

        Args:
            query: Flight search parameters

        Returns:
            List of flights sorted by price (lowest first)
        """
        # Estimate distance between airports
        distance = self._estimate_distance(query.origin, query.destination)

        # Determine number of flights to generate (3-8)
        num_flights = random.randint(3, 8)

        flights: list[Flight] = []
        for _ in range(num_flights):
            flight = self._generate_flight(
                origin=query.origin,
                destination=query.destination,
                departure_date=query.departure_date,
                distance=distance,
                booking_class=query.booking_class if hasattr(query, "booking_class") else "economy",
            )
            flights.append(flight)
            self._flights_cache[flight.id] = flight

        # Sort by price (lowest first)
        flights.sort(key=lambda f: f.price)
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
        from app.exceptions import FlightSearchError

        if flight_id not in self._flights_cache:
            raise FlightSearchError(f"Flight {flight_id} not found")
        return self._flights_cache[flight_id]

    async def check_availability(self, flight_id: str) -> bool:
        """Check if a flight is still available for booking.

        Args:
            flight_id: Unique flight identifier

        Returns:
            True if flight is available (90% chance in mock), False otherwise
        """
        # Mock: 90% of flights are available
        return flight_id in self._flights_cache and random.random() < 0.9

    async def health_check(self) -> bool:
        """Check if API is available and responding.

        Returns:
            Always True for mock client
        """
        return True

    def _estimate_distance(self, origin: str, destination: str) -> int:
        """Estimate distance between two airports in miles.

        Uses lookup table for known routes, otherwise random estimate.

        Args:
            origin: Origin IATA code
            destination: Destination IATA code

        Returns:
            Estimated distance in miles
        """
        # Try forward lookup
        if (origin, destination) in AIRPORT_DISTANCES:
            return AIRPORT_DISTANCES[(origin, destination)]

        # Try reverse lookup
        if (destination, origin) in AIRPORT_DISTANCES:
            return AIRPORT_DISTANCES[(destination, origin)]

        # Unknown route: estimate based on hash for consistency
        route_hash = hash(f"{origin}{destination}")
        return 500 + (abs(route_hash) % 2500)  # 500-3000 miles

    def _generate_flight(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        distance: int,
        booking_class: str = "economy",
    ) -> Flight:
        """Generate a realistic flight with random variation.

        Args:
            origin: Origin IATA code
            destination: Destination IATA code
            departure_date: Departure date
            distance: Distance in miles
            booking_class: Cabin class

        Returns:
            Generated Flight object
        """
        # Select random airline
        carrier, prefix = random.choice(AIRLINES)
        flight_number = f"{prefix}{random.randint(100, 9999)}"

        # Generate departure time (6am-10pm)
        hour = random.randint(6, 22)
        minute = random.choice([0, 15, 30, 45])
        departure = datetime.combine(departure_date, datetime.min.time(), tzinfo=UTC).replace(
            hour=hour, minute=minute
        )

        # Determine stops (shorter flights less likely to have stops)
        if distance < 1000:
            stops = random.choices([0, 1], weights=[0.8, 0.2])[0]
        elif distance < 2500:
            stops = random.choices([0, 1, 2], weights=[0.5, 0.4, 0.1])[0]
        else:
            stops = random.choices([0, 1, 2], weights=[0.3, 0.5, 0.2])[0]

        # Calculate duration (base + stop penalties)
        base_duration = int(distance / 500 * 60)  # ~500 mph average
        stop_penalty = stops * random.randint(45, 90)  # 45-90 min per stop
        duration_minutes = base_duration + stop_penalty

        # Calculate arrival
        arrival = departure + timedelta(minutes=duration_minutes)

        # Calculate price
        price = self._calculate_price(distance, booking_class, stops)

        return Flight(
            id=str(uuid.uuid4()),
            origin=origin,
            destination=destination,
            departure=departure,
            arrival=arrival,
            price=Decimal(str(price)),
            currency="USD",
            carrier=carrier,
            flight_number=flight_number,
            duration_minutes=duration_minutes,
            stops=stops,
            booking_class=booking_class,  # type: ignore[arg-type]
        )

    def _calculate_price(self, distance: int, booking_class: str, stops: int) -> float:
        """Calculate flight price based on distance, class, and stops.

        Args:
            distance: Distance in miles
            booking_class: Cabin class
            stops: Number of stops

        Returns:
            Price in USD
        """
        # Determine distance tier
        if distance < 1000:
            tier = "short"
        elif distance < 2500:
            tier = "medium"
        else:
            tier = "long"

        # Get base price range
        min_price, max_price = BASE_PRICES[tier]
        base_price = random.uniform(min_price, max_price)

        # Apply class multiplier
        class_multiplier = CLASS_MULTIPLIERS.get(booking_class, 1.0)
        price = base_price * class_multiplier

        # Direct flights are more expensive (premium for convenience)
        if stops == 0:
            price *= 1.2
        elif stops == 2:
            price *= 0.85  # Discount for multiple stops

        # Add some random variation (±10%)
        variation = random.uniform(0.9, 1.1)
        price *= variation

        # Round to nearest dollar
        return round(price, 2)
