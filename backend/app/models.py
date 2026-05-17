"""Pydantic models for domain and API."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.llm.errors import ProbeErrorCode

# Type aliases
BookingClass = Literal["economy", "premium_economy", "business", "first"]
SortBy = Literal["price", "duration", "departure"]


# ============================================================================
# Flight Domain Models
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


# ============================================================================
# Chat API Models
# ============================================================================


class SessionCreateRequest(BaseModel):
    """Request model for creating a new chat session.

    Per CONTEXT.md D-24, the canonical session-create payload carries four
    optional fields: provider, model, base_url (local providers only), api_key
    (cloud providers only). Per D-09, ``api_key`` lives only in session memory —
    never logged or persisted.

    Validators enforce the threat-model mitigations from PLAN.md:
    - SSRF guard on ``base_url`` (allowlist localhost / 127.0.0.1 /
      host.docker.internal; http/https schemes only).
    - Length cap on ``api_key`` (≤ 256 chars after whitespace stripping;
      empty-after-strip normalises to ``None``).
    """

    provider: str | None = Field(default=None, description="LLM provider (ollama, openai, anthropic)")
    model: str | None = Field(default=None, description="Model name for the provider")
    base_url: str | None = Field(
        default=None,
        description="Local providers only; ignored for cloud",
    )
    api_key: str | None = Field(
        default=None,
        description=(
            "Cloud providers only; ignored for local. Stored in session memory "
            "only — never logged or persisted."
        ),
    )

    @field_validator("api_key")
    @classmethod
    def _strip_and_bound_api_key(cls, v: str | None) -> str | None:
        """Strip whitespace, normalise empty to None, cap length at 256 chars."""
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 256:
            raise ValueError("api_key exceeds maximum length (256 chars)")
        return stripped

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        """SSRF guard: allowlist of {localhost, 127.0.0.1, host.docker.internal}; http/https only."""
        if v is None:
            return None
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("base_url must be http or https")
        if parsed.hostname not in {"localhost", "127.0.0.1", "host.docker.internal"}:
            raise ValueError(
                "base_url host must be localhost, 127.0.0.1, or host.docker.internal in v1"
            )
        return v


class SessionCreateError(BaseModel):
    """Structured probe failure surfaced via ``HTTPException.detail``.

    Mirrors :class:`app.services.provider_probe.ProbeError` so the OpenAPI schema
    documents the F1-F4 error envelope returned by ``POST /api/chat/session``
    when the chosen provider/model fails its pre-flight probe (Plan 04).
    """

    error: ProbeErrorCode = Field(..., description="Stable error code matching the UI-SPEC F1-F4 taxonomy")
    message: str = Field(..., description="Human-readable summary for the banner heading")
    hint: str = Field(..., description="Actionable next step for the user")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, description="User message to send to the agent")
    session_id: str = Field(..., description="Session ID for conversation continuity")


class ChatResponse(BaseModel):
    """Response model for chat endpoint (deprecated - use streaming)."""

    response: str = Field(..., description="Agent's response message")
    session_id: str = Field(..., description="Session ID for this conversation")


class StreamEvent(BaseModel):
    """Event emitted during chat streaming.

    Used for Server-Sent Events (SSE) to stream chat responses with tool visibility.
    Instead of custom metadata classes, we use LangChain's native tool_calls structure.
    """

    chunk: str = Field(default="", description="Content chunk or empty string for tool events")
    session_id: str = Field(..., description="Session ID for this conversation")
    type: Literal["content", "tool_call", "tool_result", "thinking"] = Field(
        ..., description="Type of event being streamed"
    )
    # Tool-specific fields (populated based on type)
    tool_name: str | None = Field(default=None, description="Tool name (for tool_call/result)")
    tool_args: dict[str, Any] | None = Field(default=None, description="Tool arguments (for tool_call)")
    tool_result: str | None = Field(default=None, description="Tool result text (for tool_result)")
    elapsed_ms: int | None = Field(default=None, description="Execution time in ms (for tool_result)")


# ============================================================================
# Provider Discovery / Test / Sessions API Models (Plan 04.5-06b)
# ============================================================================


class ProviderRefreshEntry(BaseModel):
    """Single provider entry in the refresh response (D-06)."""

    name: str = Field(..., description="Provider name (e.g., 'ollama', 'lmstudio').")
    models: list[str] = Field(default_factory=list, description="Discovered model ids; empty when unreachable.")
    available: bool = Field(..., description="True when the last refresh attempt succeeded for this provider.")
    error: str | None = Field(
        default=None,
        description="Wire-level error code when unreachable (e.g., 'provider_unreachable').",
    )


class ProviderRefreshResponse(BaseModel):
    """Response shape for POST /api/providers/refresh (D-06)."""

    providers: list[ProviderRefreshEntry] = Field(..., description="One entry per local provider class.")


class ProviderTestRequest(BaseModel):
    """Request payload for POST /api/providers/{provider}/test (D-14).

    api_key length is bounded to 256 chars (mirrors SessionCreateRequest's
    validator) so pathological inputs cannot exhaust memory or downstream
    cloud APIs. Whitespace is stripped before length validation.
    """

    api_key: str = Field(..., min_length=1, description="Cloud provider API key to validate.")
    model: str | None = Field(
        default=None,
        description="Optional model id; required for the Anthropic test path (researcher A8).",
    )

    @field_validator("api_key")
    @classmethod
    def _strip_and_bound_api_key(cls, v: str) -> str:
        """Strip whitespace, raise on empty-after-strip, cap length at 256 chars."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("api_key must not be empty after whitespace stripping")
        if len(stripped) > 256:
            raise ValueError("api_key exceeds maximum length (256 chars)")
        return stripped


class ProviderTestResponse(BaseModel):
    """Success response for POST /api/providers/{provider}/test (D-14).

    Failure paths raise HTTPException with a ProbeError detail; this model
    is only emitted on a 200 success.
    """

    status: Literal["ok"] = Field(..., description="Always 'ok' on the success path.")


class ChatSessionInfo(BaseModel):
    """One session entry returned by GET /api/chat/sessions (D-22, D-27)."""

    session_id: str = Field(..., description="Server-generated UUID for this session.")
    provider: str = Field(..., description="Wire-level provider name (e.g., 'ollama').")
    model: str = Field(..., description="Per-provider model identifier.")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp.")
    first_message_preview: str | None = Field(
        default=None,
        description="First HumanMessage content, truncated to 80 chars; None if session has no messages yet.",
    )


class ChatSessionsListResponse(BaseModel):
    """Response shape for GET /api/chat/sessions (D-22, D-27)."""

    sessions: list[ChatSessionInfo] = Field(..., description="Sessions owned by the authenticated user.")
