"""Unit tests for flight search tool function."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain.models import Flight, FlightQuery
from app.services.flight import FlightService
from app.tools.flight_search import create_flight_search_tool


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create mock flight service."""
    return AsyncMock(spec=FlightService)


@pytest.fixture
def sample_flights() -> list[Flight]:
    """Create sample flight data for testing."""
    from datetime import UTC, datetime

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
    ]


@pytest.mark.asyncio
async def test_tool_function_returns_formatted_results(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function returns formatted string results."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    assert isinstance(result, str)
    assert "LAX" in result
    assert "JFK" in result
    assert "American Airlines" in result
    assert "Delta Air Lines" in result
    assert "$350.00" in result
    assert "$280.00" in result


@pytest.mark.asyncio
async def test_tool_function_validates_iata_codes(mock_service: AsyncMock) -> None:
    """Test tool function validates IATA code format."""
    tool_func = create_flight_search_tool(mock_service)

    # Invalid origin (too short)
    result = await tool_func(
        origin="LA",
        destination="JFK",
        departure_date="2025-06-01",
    )
    assert "Error: Invalid origin airport code" in result
    assert "LA" in result

    # Invalid destination (contains numbers)
    result = await tool_func(
        origin="LAX",
        destination="JF1",
        departure_date="2025-06-01",
    )
    assert "Error: Invalid destination airport code" in result
    assert "JF1" in result


@pytest.mark.asyncio
async def test_tool_function_normalizes_iata_codes(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function normalizes lowercase IATA codes to uppercase."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="lax",  # lowercase
        destination="jfk",  # lowercase
        departure_date="2025-06-01",
    )

    # Should call service with uppercase codes
    call_args = mock_service.search_flights.call_args
    query: FlightQuery = call_args.kwargs["query"]
    assert query.origin == "LAX"
    assert query.destination == "JFK"
    assert isinstance(result, str)
    assert "LAX" in result


@pytest.mark.asyncio
async def test_tool_function_validates_date_format(mock_service: AsyncMock) -> None:
    """Test tool function validates date format."""
    tool_func = create_flight_search_tool(mock_service)

    # Invalid date format
    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="06/01/2025",  # Wrong format
    )
    assert "Error: Invalid date format" in result
    assert "YYYY-MM-DD" in result


@pytest.mark.asyncio
async def test_tool_function_validates_passengers(mock_service: AsyncMock) -> None:
    """Test tool function validates passenger count."""
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        passengers=0,  # Invalid
    )
    assert "Error: Number of passengers must be at least 1" in result


@pytest.mark.asyncio
async def test_tool_function_validates_sort_by(mock_service: AsyncMock) -> None:
    """Test tool function validates sort_by parameter."""
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        sort_by="invalid_sort",
    )
    assert "Error: Invalid sort_by" in result
    assert "price" in result
    assert "duration" in result
    assert "departure" in result


@pytest.mark.asyncio
async def test_tool_function_validates_max_stops(mock_service: AsyncMock) -> None:
    """Test tool function validates max_stops range."""
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        max_stops=5,  # Invalid (must be 0-2)
    )
    assert "Error: max_stops must be 0 (direct), 1, or 2" in result


@pytest.mark.asyncio
async def test_tool_function_validates_limit_range(mock_service: AsyncMock) -> None:
    """Test tool function validates limit range."""
    tool_func = create_flight_search_tool(mock_service)

    # Too high
    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        limit=50,  # Max is 20
    )
    assert "Error: Limit must be between 1 and 20" in result

    # Too low
    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        limit=0,
    )
    assert "Error: Limit must be between 1 and 20" in result


@pytest.mark.asyncio
async def test_tool_function_validates_max_duration(mock_service: AsyncMock) -> None:
    """Test tool function validates max_duration is positive."""
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        max_duration=-100,
    )
    assert "Error: max_duration must be a positive number" in result


@pytest.mark.asyncio
async def test_tool_function_validates_max_price(mock_service: AsyncMock) -> None:
    """Test tool function validates max_price is positive."""
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        max_price=-50.0,
    )
    assert "Error: max_price must be a positive number" in result


@pytest.mark.asyncio
async def test_tool_function_passes_all_parameters(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function passes all parameters to service correctly."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
        passengers=2,
        sort_by="duration",
        max_price=500.0,
        max_duration=400,
        max_stops=1,
        limit=10,
    )

    # Verify service was called with correct parameters
    call_args = mock_service.search_flights.call_args
    assert call_args.kwargs["query"].passengers == 2
    assert call_args.kwargs["sort_by"] == "duration"
    assert call_args.kwargs["max_price"] == Decimal("500.0")
    assert call_args.kwargs["max_duration"] == 400
    assert call_args.kwargs["max_stops"] == 1
    assert call_args.kwargs["limit"] == 10


@pytest.mark.asyncio
async def test_tool_function_formats_duration_correctly(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function formats flight duration in human-readable format."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    # Check duration formatting (360 minutes = 6h)
    assert "6h" in result or "6h 0m" in result
    # Check duration formatting (420 minutes = 7h)
    assert "7h" in result


@pytest.mark.asyncio
async def test_tool_function_formats_stops_correctly(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function formats stops in human-readable format."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    assert "Direct" in result  # 0 stops
    assert "1 stop" in result  # 1 stop


@pytest.mark.asyncio
async def test_tool_function_formats_times_correctly(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function formats times in 12-hour format."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    # Check for AM/PM formatting
    assert "AM" in result or "PM" in result
    # Check for colon separator
    assert ":" in result


@pytest.mark.asyncio
async def test_tool_function_handles_empty_results(mock_service: AsyncMock) -> None:
    """Test tool function handles no flights found gracefully."""
    mock_service.search_flights.return_value = []
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    assert "No flights found" in result
    assert "LAX" in result
    assert "JFK" in result
    assert "2025-06-01" in result


@pytest.mark.asyncio
async def test_tool_function_handles_flight_search_error(mock_service: AsyncMock) -> None:
    """Test tool function handles FlightSearchError gracefully."""
    from app.exceptions import FlightSearchError

    mock_service.search_flights.side_effect = FlightSearchError("API unavailable")
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    assert "Flight search error" in result
    assert "API unavailable" in result


@pytest.mark.asyncio
async def test_tool_function_handles_unexpected_error(mock_service: AsyncMock) -> None:
    """Test tool function handles unexpected exceptions gracefully."""
    mock_service.search_flights.side_effect = Exception("Unexpected error")
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    assert "Unexpected error during flight search" in result


@pytest.mark.asyncio
async def test_tool_function_includes_flight_ids(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function includes flight IDs for later reference."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    result = await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    assert "flight-1" in result
    assert "flight-2" in result
    assert "Flight ID:" in result


@pytest.mark.asyncio
async def test_tool_function_uses_default_values(
    mock_service: AsyncMock, sample_flights: list[Flight]
) -> None:
    """Test tool function uses correct default values."""
    mock_service.search_flights.return_value = sample_flights
    tool_func = create_flight_search_tool(mock_service)

    await tool_func(
        origin="LAX",
        destination="JFK",
        departure_date="2025-06-01",
    )

    # Check defaults were used
    call_args = mock_service.search_flights.call_args
    assert call_args.kwargs["query"].passengers == 1  # Default
    assert call_args.kwargs["sort_by"] == "price"  # Default
    assert call_args.kwargs["limit"] == 5  # Default
