"""Unit tests for vendor-neutral FlightSearchResult normalization (REQ-tool-json-output)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models import (
    Flight,
    FlightQuery,
    FlightResult,
    FlightSearchResult,
)
from app.tools.flight_search import (
    _extract_carrier_iata,
    _to_flight_search_result,
    _to_iso_duration,
    normalize_amadeus_offer,
    normalize_skyscanner_itinerary,
    search_flights,
)

# ---------------------------------------------------------------------------
# Acceptance fixtures
# ---------------------------------------------------------------------------

# Fixture 1: Amadeus FlightOffer (VERIFIED from amadeus4dev/amadeus-open-api-specification)
# TZ-aware datetime strings used so fromisoformat() returns aware datetimes (Pitfall 1).
AMADEUS_FLIGHT_OFFER = {
    "type": "flight-offer",
    "id": "1",
    "itineraries": [
        {
            "duration": "PT5H25M",
            "segments": [
                {
                    "id": "1",
                    "departure": {
                        "iataCode": "LAX",
                        "terminal": "B",
                        "at": "2026-06-15T08:00:00+00:00",
                    },
                    "arrival": {
                        "iataCode": "JFK",
                        "terminal": "4",
                        "at": "2026-06-15T19:25:00+00:00",
                    },
                    "carrierCode": "DL",
                    "number": "412",
                    "duration": "PT5H25M",
                    "numberOfStops": 0,
                }
            ],
        }
    ],
    "price": {
        "currency": "USD",
        "total": "450.50",
        "base": "380.00",
    },
    "travelerPricings": [
        {
            "fareDetailsBySegment": [
                {
                    "segmentId": "1",
                    "cabin": "ECONOMY",
                    "class": "Y",
                }
            ]
        }
    ],
}

AMADEUS_DICTIONARIES = {
    "carriers": {"DL": "Delta Air Lines"},
    "locations": {
        "LAX": {"cityCode": "LA", "countryCode": "US"},
        "JFK": {"cityCode": "NYC", "countryCode": "US"},
    },
}

# Fixture 2: Skyscanner Itinerary [ASSUMED — Skyscanner partner API is partner-auth-gated;
# field names based on RapidAPI playground + training knowledge. Validate against live docs
# in Phase 7 and update normalize_skyscanner_itinerary() if field names differ.]
# TZ-aware datetime strings used for consistency with Pitfall 1 guidance.
SKYSCANNER_ITINERARY = {
    "id": "iti_123",
    "legs": [
        {
            "id": "leg_1",
            "origin": {"iata": "LAX", "name": "Los Angeles International"},
            "destination": {"iata": "JFK", "name": "John F. Kennedy International"},
            "departure": "2026-06-15T08:00:00+00:00",
            "arrival": "2026-06-15T19:25:00+00:00",
            "durationInMinutes": 325,
            "stopCount": 0,
            "carriers": [{"iata": "DL", "name": "Delta Air Lines"}],
            "segments": [
                {
                    "id": "seg_1",
                    "origin": {"iata": "LAX"},
                    "destination": {"iata": "JFK"},
                    "departure": "2026-06-15T08:00:00+00:00",
                    "arrival": "2026-06-15T19:25:00+00:00",
                    "marketingCarrier": {"iata": "DL", "name": "Delta Air Lines"},
                    "flightNumber": "412",
                }
            ],
        }
    ],
    "price": {
        "raw": 450.50,
        "formatted": "$450.50",
        "currency": "USD",
    },
}

# Google Flights fixture omitted — no public REST API exists.
# Per REQ-tool-json-output: "drop the third fixture and document the omission
# if no representative sample exists."


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
    result = FlightSearchResult(
        query={"origin": "LAX", "destination": "JFK", "departure_date": "2026-06-15", "passengers": 1},
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


def test_amadeus_offer_normalizes_without_lossy_collapse() -> None:
    """normalize_amadeus_offer maps all fields without lossy collapses."""
    # Arrange
    offer = AMADEUS_FLIGHT_OFFER
    dicts = AMADEUS_DICTIONARIES

    # Act
    result: FlightResult = normalize_amadeus_offer(offer, dicts)

    # Assert
    assert result.price.amount == Decimal("450.50")
    assert result.price.currency == "USD"
    assert result.segments[0].departure.iata_code == "LAX"
    assert result.segments[0].departure.terminal == "B"
    assert result.segments[0].arrival.iata_code == "JFK"
    assert result.segments[0].arrival.terminal == "4"
    assert result.segments[0].carrier.iata_code == "DL"
    assert result.segments[0].carrier.name == "Delta Air Lines"
    assert result.booking_class == "ECONOMY"
    assert result.segments[0].number_of_stops == 0


def test_amadeus_offer_carrier_name_comes_from_dictionaries() -> None:
    """normalize_amadeus_offer resolves carrier.name from dictionaries — not just IATA code."""
    # Arrange
    offer = AMADEUS_FLIGHT_OFFER
    dicts = AMADEUS_DICTIONARIES

    # Act
    result: FlightResult = normalize_amadeus_offer(offer, dicts)

    # Assert — the lossy-collapse anti-pattern (Pitfall 3): name must not equal iata_code
    assert result.segments[0].carrier.name != result.segments[0].carrier.iata_code
    assert result.segments[0].carrier.name == "Delta Air Lines"
    assert result.segments[0].carrier.iata_code == "DL"


def test_skyscanner_itinerary_normalizes_without_lossy_collapse() -> None:
    """normalize_skyscanner_itinerary maps all fields without lossy collapses."""
    # Arrange
    itin = SKYSCANNER_ITINERARY

    # Act
    result: FlightResult = normalize_skyscanner_itinerary(itin)

    # Assert
    assert result.price.amount == Decimal("450.50")
    assert result.segments[0].departure.iata_code == "LAX"
    assert result.segments[0].carrier.iata_code == "DL"
    assert result.segments[0].carrier.name == "Delta Air Lines"
    assert result.segments[0].number_of_stops == 0


def test_skyscanner_price_decimal_precision() -> None:
    """normalize_skyscanner_itinerary converts float price.raw to exact Decimal (Pitfall 2)."""
    # Arrange — verify the fixture has a float raw price (not a string)
    raw_price = SKYSCANNER_ITINERARY["price"]["raw"]
    assert isinstance(raw_price, float), "Fixture must use float to exercise the precision guard"

    # Act
    result: FlightResult = normalize_skyscanner_itinerary(SKYSCANNER_ITINERARY)

    # Assert — Decimal("450.50") exactly, not Decimal('450.4999...')
    assert result.price.amount == Decimal("450.50"), (
        f"Expected Decimal('450.50'), got {result.price.amount!r} — float-to-Decimal coercion via str() must be applied"
    )


@pytest.mark.asyncio
async def test_search_flights_returns_json_envelope_string() -> None:
    """search_flights.ainvoke() returns a valid JSON FlightSearchResult string."""
    from app.tools.flight_client import MockFlightAPIClient

    # Arrange — inject a deterministic mock client
    search_flights._flight_client = MockFlightAPIClient(seed=42)  # type: ignore[attr-defined]

    try:
        # Act
        result = await search_flights.ainvoke(
            {
                "origin": "LAX",
                "destination": "JFK",
                "departure_date": "2026-06-15",
                "passengers": 1,
                "limit": 3,
            }
        )

        # Assert
        assert isinstance(result, str), "Tool must return a str"
        parsed = FlightSearchResult.model_validate_json(result)
        assert parsed.count >= 1
        assert parsed.status == "ok"
        assert parsed.query.origin == "LAX"

    finally:
        # Cleanup — remove injected client so other tests are unaffected
        if hasattr(search_flights, "_flight_client"):
            del search_flights._flight_client  # type: ignore[attr-defined]
