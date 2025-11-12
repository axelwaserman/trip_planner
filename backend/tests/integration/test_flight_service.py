"""Unit tests for FlightService."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain.models import Flight, FlightQuery
from app.exceptions import FlightSearchError
from app.infrastructure.clients.flight import FlightAPIClient
from app.services.flight import FlightService


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create mock flight API client."""
    return AsyncMock(spec=FlightAPIClient)


@pytest.fixture
def sample_flights() -> list[Flight]:
    """Create sample flight data for testing."""
    base_time = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)

    return [
        Flight(
            id="flight-1",
            origin="LAX",
            destination="JFK",
            departure=base_time,
            arrival=base_time.replace(hour=16),
            price=Decimal("350.00"),
            currency="USD",
            carrier="American Airlines",
            flight_number="AA100",
            duration_minutes=360,
            stops=0,
            booking_class="economy",
        ),
        Flight(
            id="flight-2",
            origin="LAX",
            destination="JFK",
            departure=base_time.replace(hour=12),
            arrival=base_time.replace(hour=19),
            price=Decimal("280.00"),
            currency="USD",
            carrier="Delta Air Lines",
            flight_number="DL200",
            duration_minutes=420,
            stops=1,
            booking_class="economy",
        ),
        Flight(
            id="flight-3",
            origin="LAX",
            destination="JFK",
            departure=base_time.replace(hour=14),
            arrival=base_time.replace(hour=22),
            price=Decimal("450.00"),
            currency="USD",
            carrier="United Airlines",
            flight_number="UA300",
            duration_minutes=480,
            stops=0,
            booking_class="business",
        ),
        Flight(
            id="flight-4",
            origin="LAX",
            destination="JFK",
            departure=base_time.replace(hour=8),
            arrival=base_time.replace(hour=17),
            price=Decimal("200.00"),
            currency="USD",
            carrier="Spirit Airlines",
            flight_number="NK400",
            duration_minutes=540,
            stops=2,
            booking_class="economy",
        ),
    ]


@pytest.mark.asyncio
async def test_search_flights_delegates_to_client(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights calls client.search()."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    await service.search_flights(query)

    mock_client.search.assert_called_once_with(query)


@pytest.mark.asyncio
async def test_search_flights_returns_sorted_by_price_default(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights sorts by price by default."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(query)

    prices = [f.price for f in results]
    assert prices == sorted(prices)
    assert results[0].id == "flight-4"  # Cheapest


@pytest.mark.asyncio
async def test_search_flights_sorts_by_duration(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights sorts by duration."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(query, sort_by="duration")

    durations = [f.duration_minutes for f in results]
    assert durations == sorted(durations)
    assert results[0].id == "flight-1"  # Shortest


@pytest.mark.asyncio
async def test_search_flights_sorts_by_departure(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights sorts by departure time."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(query, sort_by="departure")

    departure_times = [f.departure for f in results]
    assert departure_times == sorted(departure_times)
    assert results[0].id == "flight-4"  # Earliest (8am)


@pytest.mark.asyncio
async def test_search_flights_filters_by_max_price(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights filters by max_price."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(query, max_price=Decimal("300.00"))

    assert len(results) == 2  # Only flights under $300
    assert all(f.price <= Decimal("300.00") for f in results)
    assert "flight-2" in [f.id for f in results]
    assert "flight-4" in [f.id for f in results]


@pytest.mark.asyncio
async def test_search_flights_filters_by_max_duration(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights filters by max_duration."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(query, max_duration=420)

    assert len(results) == 2  # Flights with duration <= 420 minutes (360 and 420)
    assert all(f.duration_minutes <= 420 for f in results)
    assert "flight-1" in [f.id for f in results]  # 360 minutes
    assert "flight-2" in [f.id for f in results]  # 420 minutes


@pytest.mark.asyncio
async def test_search_flights_filters_by_max_stops(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights filters by max_stops."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(query, max_stops=0)

    assert len(results) == 2  # Only direct flights
    assert all(f.stops == 0 for f in results)
    assert "flight-1" in [f.id for f in results]
    assert "flight-3" in [f.id for f in results]


@pytest.mark.asyncio
async def test_search_flights_combines_filters(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights applies multiple filters together."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    results = await service.search_flights(
        query,
        max_price=Decimal("400.00"),
        max_duration=400,
        max_stops=0,
    )

    # Only flight-1 matches all criteria
    assert len(results) == 1
    assert results[0].id == "flight-1"


@pytest.mark.asyncio
async def test_search_flights_paginates_results(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights paginates results."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    # Get first page (2 results)
    page1 = await service.search_flights(query, limit=2, offset=0)
    assert len(page1) == 2

    # Get second page (2 results)
    page2 = await service.search_flights(query, limit=2, offset=2)
    assert len(page2) == 2

    # Pages should be different
    assert page1[0].id != page2[0].id


@pytest.mark.asyncio
async def test_search_flights_returns_empty_when_no_matches(
    mock_client: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test search_flights returns empty list when no flights match filters."""
    mock_client.search.return_value = sample_flights
    service = FlightService(client=mock_client)

    query = FlightQuery(origin="LAX", destination="JFK", departure_date=date(2025, 6, 1))

    # Impossible filter
    results = await service.search_flights(query, max_price=Decimal("50.00"))

    assert results == []


@pytest.mark.asyncio
async def test_get_flight_details_delegates_to_client(mock_client: AsyncMock) -> None:
    """Test get_flight_details calls client.get_flight_details()."""
    flight = Flight(
        id="test-123",
        origin="LAX",
        destination="JFK",
        departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
        arrival=datetime(2025, 6, 1, 16, 0, tzinfo=UTC),
        price=Decimal("350.00"),
        currency="USD",
        carrier="Test Air",
        flight_number="TA123",
        duration_minutes=360,
        stops=0,
        booking_class="economy",
    )
    mock_client.get_flight_details.return_value = flight
    service = FlightService(client=mock_client)

    result = await service.get_flight_details("test-123")

    mock_client.get_flight_details.assert_called_once_with("test-123")
    assert result.id == "test-123"


@pytest.mark.asyncio
async def test_get_flight_details_raises_on_not_found(mock_client: AsyncMock) -> None:
    """Test get_flight_details raises FlightSearchError for unknown ID."""
    mock_client.get_flight_details.side_effect = FlightSearchError("Flight not found")
    service = FlightService(client=mock_client)

    with pytest.raises(FlightSearchError, match="Flight not found"):
        await service.get_flight_details("unknown-id")


@pytest.mark.asyncio
async def test_check_availability_delegates_to_client(mock_client: AsyncMock) -> None:
    """Test check_availability calls client.check_availability()."""
    mock_client.check_availability.return_value = True
    service = FlightService(client=mock_client)

    result = await service.check_availability("test-123")

    mock_client.check_availability.assert_called_once_with("test-123")
    assert result is True


@pytest.mark.asyncio
async def test_check_availability_returns_false_for_unavailable(
    mock_client: AsyncMock,
) -> None:
    """Test check_availability returns False for unavailable flights."""
    mock_client.check_availability.return_value = False
    service = FlightService(client=mock_client)

    result = await service.check_availability("test-123")

    assert result is False
