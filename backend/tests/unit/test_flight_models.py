"""Tests for flight models."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Flight, FlightQuery

# Deterministic date constants — avoids freezegun dependency.
# PAST_DATE is well in the past; FUTURE_DATE is well in the future so no
# clock drift can cause a same-day boundary collision.
PAST_DATE = date(2020, 1, 1)
FUTURE_DATE = date(2099, 1, 1)

# Timezone-aware datetime constants for Flight validator tests.
_DT_DEPARTURE = datetime(2099, 6, 1, 10, 0, tzinfo=UTC)
_DT_ARRIVAL_AFTER = datetime(2099, 6, 1, 11, 0, tzinfo=UTC)  # +1 hour
_DT_ARRIVAL_SAME = datetime(2099, 6, 1, 10, 0, tzinfo=UTC)  # equal to departure
_DT_ARRIVAL_BEFORE = datetime(2099, 6, 1, 9, 0, tzinfo=UTC)  # -1 hour


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


# ---------------------------------------------------------------------------
# New validator tests — added in Phase 4.8 (REQ-pydantic-validators)
# ---------------------------------------------------------------------------


def test_flight_query_rejects_same_origin_destination() -> None:
    """FlightQuery raises ValidationError when origin and destination are identical."""
    # Arrange
    origin = "LAX"
    destination = "LAX"

    # Act / Assert
    with pytest.raises(ValidationError, match="Origin and destination must be different airports"):
        FlightQuery(origin=origin, destination=destination, departure_date=FUTURE_DATE)


def test_flight_query_rejects_same_origin_destination_after_iata_normalization() -> None:
    """FlightQuery rejects same airport even when origin is supplied in lowercase.

    validate_iata_code uppercases both fields before the model_validator runs,
    so 'lax' == 'LAX' collapses to LAX == LAX and triggers the rejection.
    """
    # Arrange — lowercase input that normalises to the same code
    origin = "lax"
    destination = "LAX"

    # Act / Assert
    with pytest.raises(ValidationError, match="Origin and destination must be different airports"):
        FlightQuery(origin=origin, destination=destination, departure_date=FUTURE_DATE)


def test_flight_query_rejects_past_departure() -> None:
    """FlightQuery raises ValidationError when departure_date is in the past."""
    # Arrange
    origin = "LAX"
    destination = "JFK"

    # Act / Assert
    with pytest.raises(ValidationError, match="Departure date cannot be in the past"):
        FlightQuery(origin=origin, destination=destination, departure_date=PAST_DATE)


def test_flight_query_accepts_today_departure() -> None:
    """FlightQuery accepts a departure_date of today (same-day bookings are valid)."""
    # Arrange — boundary condition per D-02: >= today is valid
    today = datetime.now().date()

    # Act
    query = FlightQuery(origin="LAX", destination="JFK", departure_date=today)

    # Assert
    assert query.departure_date == today


def test_flight_query_accepts_future_departure() -> None:
    """FlightQuery accepts a departure_date well in the future."""
    # Arrange
    query = FlightQuery(origin="LAX", destination="JFK", departure_date=FUTURE_DATE)

    # Assert
    assert query.departure_date == FUTURE_DATE


def test_flight_rejects_arrival_equals_departure() -> None:
    """Flight raises ValidationError when arrival datetime equals departure datetime."""
    # Arrange
    base_kwargs = dict(
        id="FL001",
        origin="LAX",
        destination="JFK",
        price=Decimal("450.00"),
        carrier="American Airlines",
        flight_number="AA123",
        duration_minutes=330,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="Arrival must be after departure"):
        Flight(**base_kwargs, departure=_DT_DEPARTURE, arrival=_DT_ARRIVAL_SAME)


def test_flight_rejects_arrival_before_departure() -> None:
    """Flight raises ValidationError when arrival datetime precedes departure datetime."""
    # Arrange
    base_kwargs = dict(
        id="FL001",
        origin="LAX",
        destination="JFK",
        price=Decimal("450.00"),
        carrier="American Airlines",
        flight_number="AA123",
        duration_minutes=330,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="Arrival must be after departure"):
        Flight(**base_kwargs, departure=_DT_DEPARTURE, arrival=_DT_ARRIVAL_BEFORE)


def test_flight_accepts_arrival_after_departure() -> None:
    """Flight constructs successfully when arrival is strictly after departure."""
    # Arrange / Act
    flight = Flight(
        id="FL001",
        origin="LAX",
        destination="JFK",
        departure=_DT_DEPARTURE,
        arrival=_DT_ARRIVAL_AFTER,
        price=Decimal("450.00"),
        carrier="American Airlines",
        flight_number="AA123",
        duration_minutes=60,
    )

    # Assert
    assert flight.arrival > flight.departure
