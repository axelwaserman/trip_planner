"""Unit tests for vendor-neutral FlightSearchResult normalization (REQ-tool-json-output).

Phase 7 / Plan 07-03 (D-08): the module-level ``normalize_amadeus_offer`` and
``normalize_skyscanner_itinerary`` helpers were deleted — vendor-specific
normalization now lives on each :class:`FlightAPIClient` impl (e.g.
``DuffelFlightClient._normalize_offer``). The regression-lock test below
prevents reintroduction.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.flights.models import (
    Flight,
    FlightQuery,
    FlightSearchResult,
)
from app.tools.flight_search import (
    _extract_carrier_iata,
    _to_flight_search_result,
    _to_iso_duration,
    search_flights,
)


def test_flight_search_module_no_amadeus_normalizers() -> None:
    """D-08 lock: vendor-specific module-level normalizers are gone."""
    from app.tools import flight_search

    assert not hasattr(flight_search, "normalize_amadeus_offer")
    assert not hasattr(flight_search, "normalize_skyscanner_itinerary")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_to_iso_duration_basic_cases() -> None:
    """_to_iso_duration converts minutes to ISO 8601 duration strings correctly."""
    # Arrange / Act / Assert — basic cases
    assert _to_iso_duration(0) == "PT0H"
    assert _to_iso_duration(60) == "PT1H"
    assert _to_iso_duration(90) == "PT1H30M"
    assert _to_iso_duration(330) == "PT5H30M"


def test_extract_carrier_iata_from_flight_number() -> None:
    """_extract_carrier_iata extracts 2-letter IATA from flight_number prefix."""
    # Arrange — flight with standard 2-letter prefix
    flight_with_prefix = Flight(
        id="FL-1",
        origin="LAX",
        destination="JFK",
        departure=datetime(2026, 6, 15, 8, 0, tzinfo=UTC),
        arrival=datetime(2026, 6, 15, 19, 25, tzinfo=UTC),
        price=Decimal("450.00"),
        carrier="Delta Air Lines",
        flight_number="DL412",
        duration_minutes=330,
    )
    # Arrange — flight with numeric-only flight number
    flight_no_prefix = Flight(
        id="FL-2",
        origin="LAX",
        destination="JFK",
        departure=datetime(2026, 6, 15, 8, 0, tzinfo=UTC),
        arrival=datetime(2026, 6, 15, 19, 25, tzinfo=UTC),
        price=Decimal("450.00"),
        carrier="Unknown",
        flight_number="412",
        duration_minutes=330,
    )

    # Act
    iata_from_prefix = _extract_carrier_iata(flight_with_prefix)
    iata_fallback = _extract_carrier_iata(flight_no_prefix)

    # Assert
    assert iata_from_prefix == "DL"
    assert iata_fallback == "ZZ"


def test_flight_search_result_envelope_shape() -> None:
    """FlightSearchResult.model_dump() exposes exactly the 4 required envelope keys."""
    # Arrange
    from app.flights.models import FlightSearchQuery

    result = FlightSearchResult(
        query=FlightSearchQuery(origin="LAX", destination="JFK", departure_date="2026-06-15", passengers=1),
        results=[],
        count=0,
    )

    # Act
    keys = set(result.model_dump().keys())

    # Assert
    assert keys == {"status", "query", "results", "count"}


def test_to_flight_search_result_preserves_flight_fields() -> None:
    """_to_flight_search_result preserves all Flight fields without loss."""
    # Arrange
    flight = Flight(
        id="FL-LAX-JFK",
        origin="LAX",
        destination="JFK",
        departure=datetime(2026, 6, 15, 8, 0, tzinfo=UTC),
        arrival=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
        price=Decimal("450.00"),
        currency="USD",
        carrier="American Airlines",
        flight_number="AA412",
        duration_minutes=330,
        stops=0,
        booking_class="economy",
    )
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2026, 6, 15),
        passengers=1,
    )

    # Act
    result = _to_flight_search_result([flight], query)

    # Assert
    assert result.count == 1
    assert result.status == "ok"
    assert result.results[0].price.amount == Decimal("450.00")
    assert result.results[0].segments[0].carrier.iata_code == "AA"
    assert result.results[0].segments[0].carrier.name == "American Airlines"
    assert result.results[0].segments[0].departure.iata_code == "LAX"
    assert result.results[0].segments[0].departure.city == "LAX"  # mock placeholder
    assert result.results[0].booking_class == "ECONOMY"  # uppercased from "economy"


def test_to_flight_search_result_empty_list() -> None:
    """_to_flight_search_result handles empty flight list by returning ok envelope."""
    # Arrange
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=date(2026, 6, 15),
        passengers=1,
    )

    # Act
    result = _to_flight_search_result([], query)

    # Assert
    assert result.count == 0
    assert result.results == []
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_search_flights_returns_json_envelope_string() -> None:
    """``search_flights(ctx, ...)`` returns a valid JSON FlightSearchResult string.

    Phase 5 / Plan 05-04: ``search_flights`` is now a plain ``async def`` whose
    first parameter is ``ctx: RunContext[ChatDeps]``. We construct a real
    :class:`pydantic_ai.RunContext` carrying a :class:`ChatDeps` populated with
    the deterministic ``MockFlightAPIClient`` and call the function directly.
    The Phase 4.x ``search_flights._flight_client`` back-door is gone (D-06).
    """
    from pydantic_ai import RunContext
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.usage import RunUsage

    from app.chat.deps import ChatDeps
    from app.tools.flight_client import MockFlightAPIClient

    # Arrange — build a RunContext with ChatDeps that carries the mock client.
    deps = ChatDeps(
        flight_client=MockFlightAPIClient(seed=42),
        conversation_id="test-session",
        user_id="test-user",
    )
    ctx: RunContext[ChatDeps] = RunContext(deps=deps, model=TestModel(), usage=RunUsage())

    # Act
    result = await search_flights(
        ctx,
        origin="LAX",
        destination="JFK",
        departure_date="2026-06-15",
        passengers=1,
        limit=3,
    )

    # Assert
    assert isinstance(result, str), "Tool must return a str"
    parsed = FlightSearchResult.model_validate_json(result)
    assert parsed.count >= 1
    assert parsed.status == "ok"
    assert parsed.query.origin == "LAX"
