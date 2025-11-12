"""Unit tests for MockFlightAPIClient."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.models import FlightQuery
from app.exceptions import FlightSearchError
from app.infrastructure.clients.mock import MockFlightAPIClient


@pytest.fixture
def mock_client() -> MockFlightAPIClient:
    """Create mock client with fixed seed for reproducible tests."""
    return MockFlightAPIClient(seed=42)


@pytest.mark.asyncio
async def test_search_returns_flights(mock_client: MockFlightAPIClient) -> None:
    """Test search returns list of flights matching query."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
        passengers=1,
    )

    flights = await mock_client.search(query)

    assert len(flights) >= 3  # Minimum 3 flights
    assert len(flights) <= 8  # Maximum 8 flights
    assert all(f.origin == "LAX" for f in flights)
    assert all(f.destination == "JFK" for f in flights)


@pytest.mark.asyncio
async def test_search_normalizes_iata_codes(mock_client: MockFlightAPIClient) -> None:
    """Test search handles lowercase IATA codes (normalized by FlightQuery)."""
    query = FlightQuery(
        origin="lax",  # Will be normalized to uppercase by FlightQuery
        destination="jfk",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    assert all(f.origin == "LAX" for f in flights)
    assert all(f.destination == "JFK" for f in flights)


@pytest.mark.asyncio
async def test_search_returns_sorted_by_price(mock_client: MockFlightAPIClient) -> None:
    """Test flights are sorted by price (lowest first)."""
    query = FlightQuery(
        origin="SFO",
        destination="SEA",
        departure_date=date(2025, 7, 15),
    )

    flights = await mock_client.search(query)

    prices = [f.price for f in flights]
    assert prices == sorted(prices)


@pytest.mark.asyncio
async def test_search_generates_valid_flight_data(mock_client: MockFlightAPIClient) -> None:
    """Test generated flights have valid data."""
    query = FlightQuery(
        origin="ORD",
        destination="DFW",
        departure_date=date(2025, 8, 10),
    )

    flights = await mock_client.search(query)

    for flight in flights:
        # Check required fields
        assert flight.id
        assert flight.carrier
        assert flight.flight_number
        assert flight.origin == "ORD"
        assert flight.destination == "DFW"

        # Check datetime fields
        assert isinstance(flight.departure, datetime)
        assert isinstance(flight.arrival, datetime)
        assert flight.departure.tzinfo == UTC
        assert flight.arrival.tzinfo == UTC
        assert flight.arrival > flight.departure

        # Check numeric fields
        assert flight.price > Decimal("0")
        assert flight.duration_minutes > 0
        assert 0 <= flight.stops <= 2

        # Check duration matches arrival - departure
        duration_delta = (flight.arrival - flight.departure).total_seconds() / 60
        assert duration_delta == pytest.approx(flight.duration_minutes, rel=0.1)


@pytest.mark.asyncio
async def test_search_varies_departure_times(mock_client: MockFlightAPIClient) -> None:
    """Test flights have varied departure times throughout the day."""
    query = FlightQuery(
        origin="LAX",
        destination="SFO",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    departure_hours = {f.departure.hour for f in flights}

    # Should have at least 2 different departure times
    assert len(departure_hours) >= 2


@pytest.mark.asyncio
async def test_search_varies_airlines(mock_client: MockFlightAPIClient) -> None:
    """Test flights include different airlines."""
    query = FlightQuery(
        origin="JFK",
        destination="LAX",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    carriers = {f.carrier for f in flights}

    # Should have at least 2 different carriers
    assert len(carriers) >= 2


@pytest.mark.asyncio
async def test_search_varies_stops(mock_client: MockFlightAPIClient) -> None:
    """Test flights include options with different stop counts."""
    # Use long-distance route to get varied stop options
    query = FlightQuery(
        origin="JFK",
        destination="LAX",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    stop_counts = {f.stops for f in flights}

    # Long routes should have at least direct and 1-stop options
    assert len(stop_counts) >= 1
    assert all(0 <= stops <= 2 for stops in stop_counts)


@pytest.mark.asyncio
async def test_search_caches_flights(mock_client: MockFlightAPIClient) -> None:
    """Test search caches flights for later retrieval."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    # All flights should be retrievable by ID
    for flight in flights:
        cached_flight = await mock_client.get_flight_details(flight.id)
        assert cached_flight.id == flight.id
        assert cached_flight.origin == flight.origin


@pytest.mark.asyncio
async def test_get_flight_details_returns_cached_flight(mock_client: MockFlightAPIClient) -> None:
    """Test get_flight_details returns flight from cache."""
    query = FlightQuery(
        origin="SFO",
        destination="LAX",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)
    flight_id = flights[0].id

    details = await mock_client.get_flight_details(flight_id)

    assert details.id == flight_id
    assert details.origin == "SFO"
    assert details.destination == "LAX"


@pytest.mark.asyncio
async def test_get_flight_details_raises_for_unknown_id(mock_client: MockFlightAPIClient) -> None:
    """Test get_flight_details raises error for unknown flight ID."""
    with pytest.raises(FlightSearchError, match="Flight .* not found"):
        await mock_client.get_flight_details("unknown-id")


@pytest.mark.asyncio
async def test_check_availability_returns_true_for_cached_flights(
    mock_client: MockFlightAPIClient,
) -> None:
    """Test check_availability returns True for most cached flights."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    # Check multiple times due to randomness (90% available)
    available_count = 0
    total_checks = 50

    for _ in range(total_checks):
        if await mock_client.check_availability(flights[0].id):
            available_count += 1

    # Should be available ~90% of the time (allow some variance)
    assert available_count >= total_checks * 0.8  # At least 80%


@pytest.mark.asyncio
async def test_check_availability_returns_false_for_unknown_id(
    mock_client: MockFlightAPIClient,
) -> None:
    """Test check_availability returns False for unknown flight ID."""
    available = await mock_client.check_availability("unknown-id")
    assert available is False


@pytest.mark.asyncio
async def test_health_check_returns_true(mock_client: MockFlightAPIClient) -> None:
    """Test health_check always returns True for mock client."""
    assert await mock_client.health_check() is True


@pytest.mark.asyncio
async def test_search_with_reproducible_seed() -> None:
    """Test search with same seed produces same results."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
    )

    client1 = MockFlightAPIClient(seed=123)
    flights1 = await client1.search(query)

    client2 = MockFlightAPIClient(seed=123)
    flights2 = await client2.search(query)

    assert len(flights1) == len(flights2)
    for f1, f2 in zip(flights1, flights2, strict=True):
        assert f1.carrier == f2.carrier
        assert f1.price == f2.price
        assert f1.departure == f2.departure


@pytest.mark.asyncio
async def test_search_without_seed_varies() -> None:
    """Test search without seed produces different results."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
    )

    client1 = MockFlightAPIClient()
    flights1 = await client1.search(query)

    client2 = MockFlightAPIClient()
    flights2 = await client2.search(query)

    # Should have different results (not guaranteed but very likely)
    prices1 = [f.price for f in flights1]
    prices2 = [f.price for f in flights2]
    assert prices1 != prices2


@pytest.mark.asyncio
async def test_short_distance_flights_have_fewer_stops(mock_client: MockFlightAPIClient) -> None:
    """Test short-distance flights tend to have fewer stops."""
    query = FlightQuery(
        origin="LAX",
        destination="SFO",  # Short distance (~337 miles)
        departure_date=date(2025, 6, 1),
    )

    flights = await mock_client.search(query)

    # Most short flights should be direct or 1 stop
    direct_or_one_stop = [f for f in flights if f.stops <= 1]
    assert len(direct_or_one_stop) >= len(flights) * 0.7  # At least 70%


@pytest.mark.asyncio
async def test_price_varies_by_stops(mock_client: MockFlightAPIClient) -> None:
    """Test direct flights tend to be more expensive than flights with stops."""
    # Run multiple searches to get statistical sample
    query = FlightQuery(
        origin="JFK",
        destination="LAX",
        departure_date=date(2025, 6, 1),
    )

    all_flights = []
    for _ in range(5):
        client = MockFlightAPIClient()  # New seed each time
        flights = await client.search(query)
        all_flights.extend(flights)

    direct_flights = [f for f in all_flights if f.stops == 0]
    one_stop_flights = [f for f in all_flights if f.stops == 1]

    if direct_flights and one_stop_flights:
        avg_direct_price = sum(f.price for f in direct_flights) / len(direct_flights)
        avg_one_stop_price = sum(f.price for f in one_stop_flights) / len(one_stop_flights)

        # Direct flights should generally be more expensive
        assert avg_direct_price > avg_one_stop_price


@pytest.mark.asyncio
async def test_flight_duration_matches_distance(mock_client: MockFlightAPIClient) -> None:
    """Test flight duration is proportional to distance."""
    # Short distance
    short_query = FlightQuery(
        origin="LAX",
        destination="SFO",
        departure_date=date(2025, 6, 1),
    )
    short_flights = await mock_client.search(short_query)

    # Long distance
    long_query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
    )
    long_flights = await mock_client.search(long_query)

    # Average duration for long flights should be significantly higher
    avg_short_duration = sum(f.duration_minutes for f in short_flights) / len(short_flights)
    avg_long_duration = sum(f.duration_minutes for f in long_flights) / len(long_flights)

    assert avg_long_duration > avg_short_duration * 3  # At least 3x longer


@pytest.mark.asyncio
async def test_departure_date_is_preserved(mock_client: MockFlightAPIClient) -> None:
    """Test all flights depart on the requested date."""
    departure_date = date(2025, 9, 15)
    query = FlightQuery(
        origin="ORD",
        destination="ATL",
        departure_date=departure_date,
    )

    flights = await mock_client.search(query)

    for flight in flights:
        assert flight.departure.date() == departure_date
