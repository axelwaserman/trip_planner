"""Flight domain models.

Provides vendor-neutral Pydantic models for flight queries, search results,
and all supporting types.  These are pure data models (Data Model Pattern) —
validators enforce domain invariants; no business logic or external I/O.

Phase 7 will introduce a real Amadeus client behind the existing
``FlightAPIClient`` ABC; these models are designed to map onto Amadeus /
Skyscanner / Google Flights response shapes without lossy field collapses.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

# Type aliases
BookingClass = Literal["economy", "premium_economy", "business", "first"]
SortBy = Literal["price", "duration", "departure"]


# ============================================================================
# Flight Query Models
# ============================================================================


class FlightQuery(BaseModel):
    """Request model for flight search.

    Attributes:
        origin: Origin airport IATA code (3 letters)
        destination: Destination airport IATA code (3 letters)
        departure_date: Departure date
        return_date: Optional return date for round trip
        passengers: Number of passengers (1-9)
    """

    origin: str = Field(..., min_length=3, max_length=3, description="Origin airport IATA code")
    destination: str = Field(..., min_length=3, max_length=3, description="Destination airport IATA code")
    departure_date: date = Field(..., description="Departure date")
    return_date: date | None = Field(default=None, description="Return date for round trip")
    passengers: int = Field(default=1, ge=1, le=9, description="Number of passengers")

    @field_validator("origin", "destination")
    @classmethod
    def validate_iata_code(cls, v: str) -> str:
        """Validate and normalize IATA airport codes.

        Converts to uppercase and validates format (3 letters A-Z).

        Args:
            v: IATA code to validate

        Returns:
            Uppercase IATA code

        Raises:
            ValueError: If code doesn't match IATA format
        """
        code = v.upper()
        if not re.match(r"^[A-Z]{3}$", code):
            raise ValueError(f"Invalid IATA code: {v}. Must be 3 letters A-Z.")
        return code

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        """Validate return date is after departure date.

        Returns:
            Validated model instance

        Raises:
            ValueError: If return date is before or same as departure date
        """
        if self.return_date and self.return_date <= self.departure_date:
            raise ValueError("Return date must be after departure date")
        return self

    @model_validator(mode="after")
    def validate_origin_destination(self) -> Self:
        """Validate origin and destination are different airports.

        Returns:
            Validated model instance

        Raises:
            ValueError: If origin and destination are the same IATA code
        """
        if self.origin == self.destination:
            raise ValueError("Origin and destination must be different airports")
        return self

    @model_validator(mode="after")
    def validate_departure_not_in_past(self) -> Self:
        """Validate departure date is not in the past.

        Same-day departures (departure_date == today) are accepted per D-02.

        Returns:
            Validated model instance

        Raises:
            ValueError: If departure_date is strictly before today
        """
        if self.departure_date < datetime.now().date():
            raise ValueError("Departure date cannot be in the past")
        return self


class Flight(BaseModel):
    """Base model for flight information.

    Pure domain model with no external dependencies.
    Contains common fields across all flight API providers.

    Attributes:
        id: Unique flight identifier
        origin: Origin airport IATA code
        destination: Destination airport IATA code
        departure: Departure datetime with timezone
        arrival: Arrival datetime with timezone
        price: Price in decimal format
        currency: ISO 4217 currency code
        carrier: Airline carrier name
        flight_number: Flight number (e.g., 'AA123')
        duration_minutes: Flight duration in minutes
        stops: Number of stops (0 for direct)
        booking_class: Cabin class (economy, business, first)
    """

    id: str = Field(..., description="Unique flight identifier")
    origin: str = Field(..., description="Origin airport IATA code")
    destination: str = Field(..., description="Destination airport IATA code")
    departure: datetime = Field(..., description="Departure datetime (with timezone)")
    arrival: datetime = Field(..., description="Arrival datetime (with timezone)")
    price: Decimal = Field(..., description="Price in decimal format")
    currency: str = Field(default="USD", description="ISO 4217 currency code")
    carrier: str = Field(..., description="Airline carrier name")
    flight_number: str = Field(..., description="Flight number (e.g., 'AA123')")
    duration_minutes: int = Field(..., ge=0, description="Flight duration in minutes")
    stops: int = Field(default=0, ge=0, description="Number of stops (0 for direct)")
    booking_class: BookingClass = Field(default="economy", description="Cabin class (economy, business, first)")

    @field_validator("booking_class", mode="before")
    @classmethod
    def normalize_booking_class(cls, v: str | BookingClass) -> BookingClass:
        """Normalize booking class to lowercase for case-insensitive input.

        Args:
            v: Booking class to normalize

        Returns:
            Lowercase booking class

        Raises:
            ValueError: If booking class is not valid
        """
        if isinstance(v, str):
            normalized = v.lower()
            valid_classes = {"economy", "premium_economy", "business", "first"}
            if normalized not in valid_classes:
                raise ValueError(f"Invalid booking class: {v}. Must be one of {valid_classes}")
            return normalized  # type: ignore[return-value]
        return v

    @model_validator(mode="after")
    def validate_arrival_after_departure(self) -> Self:
        """Validate arrival datetime is strictly after departure datetime.

        Returns:
            Validated model instance

        Raises:
            ValueError: If arrival is at or before departure
        """
        if self.arrival <= self.departure:
            raise ValueError("Arrival must be after departure")
        return self


# ============================================================================
# Flight Search Result Models (Vendor-Neutral)
# ============================================================================


class FlightEndpoint(BaseModel):
    """Departure or arrival endpoint for a flight segment.

    Maps to Amadeus ``FlightEndPoint`` schema. Used for both departure and
    arrival in each ``FlightSegment``.

    Attributes:
        iata_code: IATA airport code (3 letters, e.g. ``"LAX"``).
        city: City name. Mock data uses the IATA code as a placeholder;
            Phase 7 Amadeus client populates this from ``dictionaries.locations``.
        terminal: Terminal name or number, e.g. ``"B"`` or ``"4"`` (optional).
        at: Local ISO-8601 datetime with timezone offset (UTC for mock data).
            Note: Amadeus returns naive local datetimes — the Phase 7 normalizer
            must append a timezone offset from airport lookup.
    """

    iata_code: str = Field(..., min_length=3, max_length=3, description="IATA airport code")
    city: str = Field(..., description="City name; mock uses IATA code as placeholder")
    terminal: str | None = Field(default=None, description="Terminal name/number (optional)")
    at: datetime = Field(..., description="Local ISO-8601 datetime with timezone (UTC for mock data)")


class CarrierInfo(BaseModel):
    """Airline carrier identification with both code and display name.

    Attributes:
        iata_code: IATA 2-letter airline code, e.g. ``"DL"``.
        name: Display name, e.g. ``"Delta Air Lines"``. Resolved from Amadeus
            ``dictionaries.carriers`` in the Phase 7 normalizer.
    """

    iata_code: str = Field(..., min_length=2, max_length=2, description="IATA 2-letter airline code, e.g. 'DL'")
    name: str = Field(..., description="Display name, e.g. 'Delta Air Lines'")


class PriceInfo(BaseModel):
    """Price information using Decimal to avoid float precision loss.

    Attributes:
        amount: Total price as an exact Decimal. Float input (e.g. from
            Skyscanner ``price.raw``) is coerced via ``Decimal(str(v))`` to
            avoid ``Decimal(450.50) == Decimal('450.499...')`` noise.
        currency: ISO 4217 currency code, defaults to ``"USD"``.
    """

    amount: Decimal = Field(..., description="Total price (Decimal to avoid float precision loss)")
    currency: str = Field(default="USD", description="ISO 4217 currency code")

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_float_to_decimal(cls, v: Decimal | float | str) -> Decimal:
        """Coerce float or string input to Decimal via str() to avoid precision loss.

        Args:
            v: Raw amount value (Decimal pass-through, float coerced via str).

        Returns:
            Exact Decimal representation of the amount.
        """
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class FlightSegment(BaseModel):
    """A single flight leg within a journey.

    Maps to Amadeus ``Segment`` schema. A direct flight has exactly one segment;
    a connecting itinerary has one segment per leg.

    Attributes:
        id: Segment identifier (from the carrier or generated for mock data).
        departure: Departure endpoint with IATA code, city, terminal, and datetime.
        arrival: Arrival endpoint with IATA code, city, terminal, and datetime.
        carrier: Carrier IATA code and display name.
        flight_number: Flight number as assigned by carrier, e.g. ``"DL412"``.
        duration: ISO 8601 duration string, e.g. ``"PT5H30M"``.
        number_of_stops: Number of technical stops (0 for direct). Must be >= 0.
    """

    id: str = Field(..., description="Segment identifier")
    departure: FlightEndpoint = Field(..., description="Departure endpoint")
    arrival: FlightEndpoint = Field(..., description="Arrival endpoint")
    carrier: CarrierInfo = Field(..., description="Carrier IATA code and display name")
    flight_number: str = Field(..., description="Flight number as assigned by carrier, e.g. 'DL412'")
    duration: str = Field(..., description="ISO 8601 duration string, e.g. 'PT5H30M'")
    number_of_stops: int = Field(default=0, ge=0, description="Number of technical stops (>= 0)")


class FlightResult(BaseModel):
    """A single bookable flight offer, normalised across all vendor schemas.

    Attributes:
        id: Unique offer identifier.
        segments: Ordered list of flight segments (min 1). One segment for
            direct flights; multiple for connecting itineraries.
        total_duration: Total journey duration as ISO 8601 string, e.g. ``"PT5H30M"``.
        price: Price information (amount and currency).
        booking_class: Cabin class as a string (not Literal) so the schema
            stays additively extensible without breaking changes.
    """

    id: str = Field(..., description="Unique offer identifier")
    segments: list[FlightSegment] = Field(..., min_length=1, description="Flight segments (min 1)")
    total_duration: str = Field(..., description="Total journey duration (ISO 8601)")
    price: PriceInfo = Field(..., description="Price information")
    booking_class: str = Field(
        default="ECONOMY",
        description="Cabin class — string not Literal so the schema stays additively extensible",
    )


class FlightSearchQuery(BaseModel):
    """Echo of the search request parameters included in the result envelope.

    Attributes:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date as ISO date string echoing the request.
        passengers: Number of passengers requested (>= 1).
    """

    origin: str = Field(..., description="Origin airport IATA code")
    destination: str = Field(..., description="Destination airport IATA code")
    departure_date: str = Field(..., description="Departure date as ISO date string echoing the request")
    passengers: int = Field(default=1, ge=1, description="Number of passengers requested")


class FlightSearchResult(BaseModel):
    """Canonical envelope returned by ``search_flights()``.

    Serialised via ``model_dump_json()`` for the SSE ``tool_result`` event.
    The frontend ``ToolExecutionCard`` parses this JSON to render a structured
    flight results table.

    Attributes:
        status: Result status, defaults to ``"ok"``.
        query: Echo of the search request parameters.
        results: List of bookable flight offers (empty list if none found).
        count: Number of results returned (>= 0).
    """

    status: str = Field(default="ok", description="Result status")
    query: FlightSearchQuery = Field(..., description="Echo of the search request parameters")
    results: list[FlightResult] = Field(..., description="List of bookable flight offers")
    count: int = Field(..., ge=0, description="Number of results returned")
