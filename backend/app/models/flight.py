"""Flight domain models for trip planning."""

import re
from datetime import date, datetime
from decimal import Decimal

import pydantic
from pydantic import BaseModel, Field, field_validator


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
    destination: str = Field(
        ..., min_length=3, max_length=3, description="Destination airport IATA code"
    )
    departure_date: date = Field(..., description="Departure date")
    return_date: date | None = Field(None, description="Return date for round trip")
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

    @field_validator("return_date")
    @classmethod
    def validate_return_date(
        cls, v: date | None, info: pydantic.ValidationInfo
    ) -> date | None:
        """Validate return date is after departure date.

        Args:
            v: Return date to validate
            info: Validation info containing other fields

        Returns:
            Validated return date

        Raises:
            ValueError: If return date is before or same as departure date
        """
        if v is not None and "departure_date" in info.data:
            departure = info.data["departure_date"]
            if v <= departure:
                raise ValueError("Return date must be after departure date")
        return v


class Flight(BaseModel):
    """Base model for flight information.

    This is the base class that all flight implementations inherit from.
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
    booking_class: str = Field(
        default="economy", description="Cabin class (economy, business, first)"
    )

    @field_validator("booking_class")
    @classmethod
    def validate_booking_class(cls, v: str) -> str:
        """Validate booking class is one of the allowed values.

        Args:
            v: Booking class to validate

        Returns:
            Lowercase booking class

        Raises:
            ValueError: If booking class is not valid
        """
        allowed = {"economy", "premium_economy", "business", "first"}
        normalized = v.lower()
        if normalized not in allowed:
            raise ValueError(f"Invalid booking class: {v}. Must be one of {allowed}")
        return normalized


class MockFlight(Flight):
    """Mock flight model for testing and development.

    Inherits all fields from Flight base model.
    Currently no additional fields, but structured for future extensions.
    """


class AmadeusFlight(Flight):
    """Amadeus API flight model.

    Extends base Flight model with Amadeus-specific fields.
    Will be used in Phase 5 when integrating real Amadeus API.

    Additional fields can be added here for Amadeus-specific data like:
    - Baggage allowance
    - Seat availability
    - Fare rules
    """
