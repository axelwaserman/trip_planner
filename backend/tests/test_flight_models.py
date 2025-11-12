"""Tests for flight models."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.models import Flight, FlightQuery


def test_flight_query_valid() -> None:
    """Test FlightQuery with valid data."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
        return_date=date(2025, 6, 8),
        passengers=2,
    )
    assert query.origin == "LAX"
    assert query.destination == "JFK"
    assert query.passengers == 2


def test_flight_query_iata_code_uppercase() -> None:
    """Test FlightQuery converts IATA codes to uppercase."""
    query = FlightQuery(
        origin="lax",
        destination="jfk",
        departure_date=date(2025, 6, 1),
    )
    assert query.origin == "LAX"
    assert query.destination == "JFK"


def test_flight_query_invalid_iata_code() -> None:
    """Test FlightQuery rejects invalid IATA codes."""
    # Too long
    with pytest.raises(ValidationError, match="String should have at most 3 characters"):
        FlightQuery(
            origin="LAXX",
            destination="JFK",
            departure_date=date(2025, 6, 1),
        )

    # Too short
    with pytest.raises(ValidationError, match="String should have at least 3 characters"):
        FlightQuery(
            origin="LA",
            destination="JFK",
            departure_date=date(2025, 6, 1),
        )

    # Contains digit - this gets past length validation but caught by regex
    with pytest.raises(ValidationError, match="Invalid IATA code"):
        FlightQuery(
            origin="L4X",
            destination="JFK",
            departure_date=date(2025, 6, 1),
        )


def test_flight_query_return_before_departure() -> None:
    """Test FlightQuery rejects return date before departure."""
    with pytest.raises(ValidationError, match="Return date must be after departure date"):
        FlightQuery(
            origin="LAX",
            destination="JFK",
            departure_date=date(2025, 6, 8),
            return_date=date(2025, 6, 1),  # Before departure
        )


def test_flight_query_return_same_as_departure() -> None:
    """Test FlightQuery rejects return date same as departure."""
    with pytest.raises(ValidationError, match="Return date must be after departure date"):
        FlightQuery(
            origin="LAX",
            destination="JFK",
            departure_date=date(2025, 6, 1),
            return_date=date(2025, 6, 1),  # Same day
        )


def test_flight_query_passengers_range() -> None:
    """Test FlightQuery validates passenger count range."""
    # Valid range
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
        passengers=9,
    )
    assert query.passengers == 9

    # Too many passengers
    with pytest.raises(ValidationError):
        FlightQuery(
            origin="LAX",
            destination="JFK",
            departure_date=date(2025, 6, 1),
            passengers=10,
        )

    # Too few passengers
    with pytest.raises(ValidationError):
        FlightQuery(
            origin="LAX",
            destination="JFK",
            departure_date=date(2025, 6, 1),
            passengers=0,
        )


def test_flight_query_default_passengers() -> None:
    """Test FlightQuery defaults to 1 passenger."""
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2025, 6, 1),
    )
    assert query.passengers == 1


def test_flight_valid() -> None:
    """Test Flight model with valid data."""
    flight = Flight(
        id="FL123",
        origin="LAX",
        destination="JFK",
        departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
        arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
        price=Decimal("450.00"),
        currency="USD",
        carrier="American Airlines",
        flight_number="AA123",
        duration_minutes=330,
        stops=0,
        booking_class="economy",
    )
    assert flight.id == "FL123"
    assert flight.price == Decimal("450.00")
    assert flight.duration_minutes == 330


def test_flight_default_values() -> None:
    """Test Flight model default values."""
    flight = Flight(
        id="FL123",
        origin="LAX",
        destination="JFK",
        departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
        arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
        price=Decimal("450.00"),
        carrier="American Airlines",
        flight_number="AA123",
        duration_minutes=330,
    )
    assert flight.currency == "USD"
    assert flight.stops == 0
    assert flight.booking_class == "economy"


def test_flight_booking_class_validation() -> None:
    """Test Flight validates booking class."""
    # Valid classes
    for booking_class in ["economy", "premium_economy", "business", "first"]:
        flight = Flight(
            id="FL123",
            origin="LAX",
            destination="JFK",
            departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
            arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
            price=Decimal("450.00"),
            carrier="American Airlines",
            flight_number="AA123",
            duration_minutes=330,
            booking_class=booking_class,  # type: ignore[arg-type]
        )
        assert flight.booking_class == booking_class

    # Invalid class
    with pytest.raises(ValidationError, match="Invalid booking class"):
        Flight(
            id="FL123",
            origin="LAX",
            destination="JFK",
            departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
            arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
            price=Decimal("450.00"),
            carrier="American Airlines",
            flight_number="AA123",
            duration_minutes=330,
            booking_class="super_deluxe",  # type: ignore[arg-type]
        )


def test_flight_booking_class_case_insensitive() -> None:
    """Test Flight normalizes booking class to lowercase."""
    flight = Flight(
        id="FL123",
        origin="LAX",
        destination="JFK",
        departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
        arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
        price=Decimal("450.00"),
        carrier="American Airlines",
        flight_number="AA123",
        duration_minutes=330,
        booking_class="BUSINESS",  # type: ignore[arg-type]
    )
    assert flight.booking_class == "business"


def test_flight_negative_duration() -> None:
    """Test Flight rejects negative duration."""
    with pytest.raises(ValidationError):
        Flight(
            id="FL123",
            origin="LAX",
            destination="JFK",
            departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
            arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
            price=Decimal("450.00"),
            carrier="American Airlines",
            flight_number="AA123",
            duration_minutes=-30,
        )


def test_flight_negative_stops() -> None:
    """Test Flight rejects negative stops."""
    with pytest.raises(ValidationError):
        Flight(
            id="FL123",
            origin="LAX",
            destination="JFK",
            departure=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
            arrival=datetime(2025, 6, 1, 18, 30, tzinfo=UTC),
            price=Decimal("450.00"),
            carrier="American Airlines",
            flight_number="AA123",
            duration_minutes=330,
            stops=-1,
        )


def test_flight_model_validate() -> None:
    """Test Flight.model_validate() for parsing API responses."""
    data = {
        "id": "FL123",
        "origin": "LAX",
        "destination": "JFK",
        "departure": "2025-06-01T10:00:00+00:00",
        "arrival": "2025-06-01T18:30:00+00:00",
        "price": "450.00",
        "currency": "USD",
        "carrier": "American Airlines",
        "flight_number": "AA123",
        "duration_minutes": 330,
        "stops": 0,
        "booking_class": "economy",
    }
    flight = Flight.model_validate(data)
    assert flight.id == "FL123"
    assert flight.price == Decimal("450.00")
    assert isinstance(flight.departure, datetime)
