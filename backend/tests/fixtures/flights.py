"""Test fixtures for flight domain models."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.flights.models import Flight, FlightQuery

_DEFAULT_DEPARTURE = datetime(2099, 6, 1, 10, 0, tzinfo=UTC)
_DEFAULT_ARRIVAL = datetime(2099, 6, 1, 18, 30, tzinfo=UTC)  # +8h30m (510 min)


def create_mock_flight(
    *,
    id: str = "FL001",
    origin: str = "LAX",
    destination: str = "JFK",
    departure: datetime = _DEFAULT_DEPARTURE,
    arrival: datetime = _DEFAULT_ARRIVAL,
    price: Decimal = Decimal("450.00"),
    currency: str = "USD",
    carrier: str = "Test Airlines",
    flight_number: str = "TA100",
    duration_minutes: int = 510,
    stops: int = 0,
    booking_class: str = "economy",
) -> Flight:
    """Return a Flight with sensible defaults; override any field with keyword arguments."""
    return Flight(
        id=id,
        origin=origin,
        destination=destination,
        departure=departure,
        arrival=arrival,
        price=price,
        currency=currency,
        carrier=carrier,
        flight_number=flight_number,
        duration_minutes=duration_minutes,
        stops=stops,
        booking_class=booking_class,  # type: ignore[arg-type]
    )


def create_mock_flight_query(
    *,
    origin: str = "LAX",
    destination: str = "JFK",
    departure_date: date = date(2099, 6, 1),
    return_date: date | None = None,
    passengers: int = 1,
) -> FlightQuery:
    """Return a FlightQuery with sensible defaults; override any field with keyword arguments."""
    return FlightQuery(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        passengers=passengers,
    )
