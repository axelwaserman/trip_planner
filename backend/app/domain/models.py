"""Flight domain models for trip planning."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.types import BookingClass


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
    booking_class: BookingClass = Field(
        default="economy", description="Cabin class (economy, business, first)"
    )

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
