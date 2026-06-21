"""Flight search tool for the PydanticAI chat agent.

Phase 5 / Plan 05-04: this module retired the LangChain ``@tool`` decorator
and the Phase 4.x monkey-patched attribute back-door. The function now reads
its :class:`FlightAPIClient` collaborator from ``ctx.deps.flight_client`` —
PydanticAI threads :class:`app.chat.deps.ChatDeps` through ``RunContext`` once
per turn (D-06).

Closes ARCHITECTURE.md "Monkey-Patched Tool Dependency" Known Tech Debt.

Import-cycle note: PydanticAI resolves the ``ctx: RunContext[ChatDeps]``
annotation via :func:`typing.get_type_hints` at ``Agent`` construction time,
which evaluates the deferred string annotation in this module's globals — so
``ChatDeps`` must be a real runtime symbol here, not a ``TYPE_CHECKING``-only
import. To avoid the ``app.chat`` ↔ ``app.tools.flight_search`` cycle,
:mod:`app.chat.service` imports ``search_flights`` LAZILY inside
:meth:`ChatService.create_session`. Importing :mod:`app.chat.deps` directly
here is safe because ``deps.py`` itself has no transitive dependency on this
module.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic_ai import (
    RunContext,  # noqa: TC002 - PydanticAI evaluates RunContext[ChatDeps] via get_type_hints at Agent construction time; runtime import required (see module docstring)
)

from app.chat.deps import ChatDeps  # noqa: TC001 - same reason as RunContext above; ChatDeps must be a runtime symbol
from app.exceptions import FlightSearchError
from app.flights.models import (
    CarrierInfo,
    Flight,
    FlightEndpoint,
    FlightQuery,
    FlightResult,
    FlightSearchQuery,
    FlightSearchResult,
    FlightSegment,
    PriceInfo,
    SortBy,
)


def _extract_carrier_iata(flight: Flight) -> str:
    """Extract a 2-letter IATA carrier code from the flight number prefix.

    Best-effort: matches the leading two uppercase letters of the flight number.
    Falls back to ``"ZZ"`` when the flight number has no leading letter pair
    (e.g. numeric-only flight numbers from non-standard data).

    Args:
        flight: Flight domain model whose ``flight_number`` is inspected.

    Returns:
        Two-letter IATA carrier code (e.g. ``"DL"`` from ``"DL412"``) or
        ``"ZZ"`` when no match is found.
    """
    m = re.match(r"^([A-Z]{2})", flight.flight_number)
    return m.group(1) if m else "ZZ"


def _to_iso_duration(minutes: int) -> str:
    """Convert a duration in minutes to an ISO 8601 duration string.

    Args:
        minutes: Duration in minutes (>= 0).

    Returns:
        ISO 8601 duration string, e.g. ``"PT5H30M"`` for 330 minutes,
        ``"PT1H"`` for 60 minutes, ``"PT0H"`` for 0 minutes.
    """
    h, m = divmod(minutes, 60)
    return f"PT{h}H{m}M" if m else f"PT{h}H"


def _to_flight_search_result(flights: list[Flight], query: FlightQuery) -> FlightSearchResult:
    """Translate a list of mock Flight objects into a vendor-neutral FlightSearchResult.

    Each ``Flight`` becomes exactly one ``FlightResult`` with one ``FlightSegment``.
    The mock client does not provide city names, so both ``city`` and ``iata_code``
    are set to the airport's IATA code as a placeholder. Phase 7's real Amadeus
    client will populate ``city`` from ``dictionaries.locations``.

    Args:
        flights: List of ``Flight`` objects returned by the ``FlightAPIClient``.
        query: The original ``FlightQuery`` used for the search; echoed in the
            result envelope.

    Returns:
        A fully-populated ``FlightSearchResult`` envelope with ``status="ok"``,
        the echoed query, and one ``FlightResult`` per input flight.
    """
    results: list[FlightResult] = []
    for flight in flights:
        iata = _extract_carrier_iata(flight)
        results.append(
            FlightResult(
                id=flight.id,
                segments=[
                    FlightSegment(
                        id=f"{flight.id}-s1",
                        departure=FlightEndpoint(
                            iata_code=flight.origin,
                            city=flight.origin,  # mock placeholder — real client uses city lookup
                            at=flight.departure,
                        ),
                        arrival=FlightEndpoint(
                            iata_code=flight.destination,
                            city=flight.destination,  # mock placeholder
                            at=flight.arrival,
                        ),
                        carrier=CarrierInfo(iata_code=iata, name=flight.carrier),
                        flight_number=flight.flight_number,
                        duration=_to_iso_duration(flight.duration_minutes),
                        number_of_stops=flight.stops,
                    )
                ],
                total_duration=_to_iso_duration(flight.duration_minutes),
                price=PriceInfo(amount=flight.price, currency=flight.currency),
                booking_class=flight.booking_class.upper(),
            )
        )
    return FlightSearchResult(
        status="ok",
        query=FlightSearchQuery(
            origin=query.origin,
            destination=query.destination,
            departure_date=str(query.departure_date),
            passengers=query.passengers,
        ),
        results=results,
        count=len(results),
    )


def normalize_amadeus_offer(offer: dict[str, Any], dictionaries: dict[str, Any]) -> FlightResult:
    """Normalize an Amadeus FlightOffer dict into a vendor-neutral FlightResult.

    Reads carrier names from the ``dictionaries.carriers`` lookup and city names
    from ``dictionaries.locations`` to avoid lossy field collapses (Pitfall 3).
    Booking class is extracted from ``travelerPricings[0].fareDetailsBySegment[0].cabin``.

    Args:
        offer: A single Amadeus ``FlightOffer`` dict (from ``response.data[]``).
        dictionaries: The Amadeus response ``dictionaries`` object containing
            ``carriers`` and ``locations`` lookup dicts.

    Returns:
        A single ``FlightResult`` with normalized segments, price, and booking class.

    Note:
        Amadeus ``departure.at`` is a local datetime string with no TZ offset.
        The Phase 4.6 test fixture supplies TZ-aware strings so this phase is
        exercised correctly. Phase 7 must attach a TZ from airport lookup for
        production use.
    """
    itinerary = offer["itineraries"][0]
    total_duration: str = itinerary["duration"]
    booking_class: str = offer["travelerPricings"][0]["fareDetailsBySegment"][0]["cabin"]
    price_amount = Decimal(str(offer["price"]["total"]))
    price_currency: str = offer["price"]["currency"]

    segments: list[FlightSegment] = []
    for seg in itinerary["segments"]:
        carrier_code: str = seg["carrierCode"]
        carrier_name: str = dictionaries["carriers"].get(carrier_code, carrier_code)

        dep_iata: str = seg["departure"]["iataCode"]
        arr_iata: str = seg["arrival"]["iataCode"]
        dep_city: str = dictionaries["locations"].get(dep_iata, {}).get("cityCode", dep_iata)
        arr_city: str = dictionaries["locations"].get(arr_iata, {}).get("cityCode", arr_iata)

        dep_terminal: str | None = seg["departure"].get("terminal")
        arr_terminal: str | None = seg["arrival"].get("terminal")

        dep_at: datetime = datetime.fromisoformat(seg["departure"]["at"])
        arr_at: datetime = datetime.fromisoformat(seg["arrival"]["at"])

        segments.append(
            FlightSegment(
                id=seg["id"],
                departure=FlightEndpoint(
                    iata_code=dep_iata,
                    city=dep_city,
                    terminal=dep_terminal,
                    at=dep_at,
                ),
                arrival=FlightEndpoint(
                    iata_code=arr_iata,
                    city=arr_city,
                    terminal=arr_terminal,
                    at=arr_at,
                ),
                carrier=CarrierInfo(iata_code=carrier_code, name=carrier_name),
                flight_number=seg["number"],
                duration=seg["duration"],
                number_of_stops=seg.get("numberOfStops", 0),
            )
        )

    return FlightResult(
        id=offer["id"],
        segments=segments,
        total_duration=total_duration,
        price=PriceInfo(amount=price_amount, currency=price_currency),
        booking_class=booking_class,
    )


def normalize_skyscanner_itinerary(itin: dict[str, Any]) -> FlightResult:
    """Normalize a Skyscanner itinerary dict into a vendor-neutral FlightResult.

    Skyscanner uses ``itinerary.legs[]`` where each leg maps to an O/D pair
    (equivalent to an Amadeus ``itinerary``). The leg's nested ``segments[]``
    map to our ``FlightResult.segments[]``. This avoids the extra nesting level
    confusion described in RESEARCH.md Pitfall 6.

    For per-segment duration, the leg-level ``durationInMinutes`` is applied to
    the first segment; any additional segments receive ``"PT0H"`` as a fallback
    (leg-level breakdown by segment is not provided in the Skyscanner fixture).

    Args:
        itin: A single Skyscanner itinerary dict (assumed field names per
            RESEARCH.md Fixture 2 — field names are [ASSUMED] from RapidAPI
            playground; validate against live API docs in Phase 7).

    Returns:
        A single ``FlightResult`` normalized from the first leg of the itinerary.
    """
    from datetime import datetime  # local import to avoid polluting module namespace

    legs: list[dict[str, Any]] = itin.get("legs", [])
    if not legs:
        raise ValueError("Skyscanner itinerary has no legs; cannot normalize.")
    leg = legs[0]
    total_duration: str = _to_iso_duration(leg["durationInMinutes"])
    price_amount = Decimal(str(itin["price"]["raw"]))
    price_currency: str = itin["price"]["currency"]

    # Leg-level carrier for segments that don't have per-segment carrier info
    leg_carrier = leg["carriers"][0] if leg.get("carriers") else {"iata": "ZZ", "name": "Unknown"}

    segments: list[FlightSegment] = []
    leg_segments: list[dict[str, Any]] = leg.get("segments", [])
    if not leg_segments:
        raise ValueError(f"Skyscanner leg '{leg.get('id')}' has no segments; cannot normalize.")
    for idx, seg in enumerate(leg_segments):
        seg_carrier = seg.get("marketingCarrier", leg_carrier)
        carrier_iata: str = seg_carrier.get("iata", "ZZ")
        carrier_name: str = seg_carrier.get("name", carrier_iata)

        origin_iata: str = seg["origin"]["iata"]
        dest_iata: str = seg["destination"]["iata"]
        # Use name from leg endpoints (leg has richer city info than per-segment origin)
        origin_city: str = leg["origin"].get("name", origin_iata) if idx == 0 else origin_iata
        dest_city: str = leg["destination"].get("name", dest_iata) if idx == len(leg_segments) - 1 else dest_iata

        dep_at: datetime = datetime.fromisoformat(seg["departure"])
        arr_at: datetime = datetime.fromisoformat(seg["arrival"])

        # Apply leg duration to first segment; "PT0H" for additional segments
        seg_duration: str = total_duration if idx == 0 else "PT0H"

        segments.append(
            FlightSegment(
                id=seg["id"],
                departure=FlightEndpoint(
                    iata_code=origin_iata,
                    city=origin_city,
                    at=dep_at,
                ),
                arrival=FlightEndpoint(
                    iata_code=dest_iata,
                    city=dest_city,
                    at=arr_at,
                ),
                carrier=CarrierInfo(iata_code=carrier_iata, name=carrier_name),
                flight_number=seg["flightNumber"],
                duration=seg_duration,
                number_of_stops=seg.get("numberOfStops", leg.get("stopCount", 0)),
            )
        )

    return FlightResult(
        id=itin["id"],
        segments=segments,
        total_duration=total_duration,
        price=PriceInfo(amount=price_amount, currency=price_currency),
        booking_class="ECONOMY",  # Skyscanner fixture does not expose cabin class
    )


async def search_flights(
    ctx: RunContext[ChatDeps],
    origin: str,
    destination: str,
    departure_date: str,
    passengers: int = 1,
    sort_by: str = "price",
    max_price: float | None = None,
    max_duration: int | None = None,
    max_stops: int | None = None,
    limit: int = 5,
) -> str:
    """Search for flights between two airports.

    **When to use this tool:**
    - User asks about flights, airfare, or travel options between cities/airports
    - User wants to compare flight options or find the best flights
    - User requests specific flight information (prices, times, duration, airlines)

    **When NOT to use this tool:**
    - General greetings or small talk ("Hello", "How are you?")
    - Questions about hotels, cars, restaurants, or non-flight travel
    - Already have flight search results and user is just asking follow-up questions about them

    **Handling ambiguous requests:**
    - If city name is provided instead of IATA code, infer the most likely major airport:
      * "Los Angeles" or "LA" → "LAX"
      * "New York" or "NYC" → "JFK"
      * "San Francisco" or "SF" → "SFO"
      * "Chicago" → "ORD"
      * "Miami" → "MIA"
      * "Seattle" → "SEA"
      * "Boston" → "BOS"
    - If origin, destination, or date is missing, ask the user for clarification
    - If date is relative ("tomorrow", "next week"), calculate the actual date based on TODAY'S DATE
    - If user says "flights to X" without origin, ask where they're flying from
    - If date format is wrong (like MM/DD/YYYY), convert it to YYYY-MM-DD

    **Expected output format:**
    Returns a JSON-serialized FlightSearchResult envelope:
    ``{status, query, results[], count}``. Each result has IATA endpoints,
    ISO-8601 timestamps, segments[], price{amount,currency}, carrier{iata_code,name}.
    The LLM should narrate this structured data naturally to the user — the
    structured card renders alongside the prose response.

    Args:
        origin: Origin airport IATA code (3 letters, e.g., "LAX", "JFK")
        destination: Destination airport IATA code (3 letters, e.g., "SFO", "ORD")
        departure_date: Departure date in YYYY-MM-DD format (e.g., "2025-06-15")
        passengers: Number of passengers (default: 1, min: 1, max: 9)
        sort_by: Sort results by "price" (default), "duration", or "departure"
        max_price: Optional maximum price filter in USD (e.g., 500.00)
        max_duration: Optional maximum duration filter in minutes (e.g., 360 for 6 hours)
        max_stops: Optional maximum number of stops - 0 (direct only), 1, or 2 (default: no filter)
        limit: Maximum number of results to return (default: 5, max: 20)

    Returns:
        JSON string (FlightSearchResult.model_dump_json()) on success, or a plain error
        string on failure. Always returns a string.
    """
    # PydanticAI threads ChatDeps through RunContext per turn (D-06).
    # The Phase 4.x attribute back-door is closed; the deps client is non-None by type.
    client = ctx.deps.flight_client

    try:
        # Validate and parse inputs
        try:
            departure_date_obj = date.fromisoformat(departure_date)
        except ValueError as e:
            return f"Error: Invalid date format '{departure_date}'. Please use YYYY-MM-DD format (e.g., '2025-06-15'). Details: {e}"

        # Validate IATA codes (basic check)
        if len(origin) != 3 or not origin.isalpha():
            return (
                f"Error: Invalid origin airport code '{origin}'. Must be 3 letters (e.g., 'LAX')."
            )
        if len(destination) != 3 or not destination.isalpha():
            return f"Error: Invalid destination airport code '{destination}'. Must be 3 letters (e.g., 'JFK')."

        origin = origin.upper()
        destination = destination.upper()

        # Validate sort_by
        valid_sort_by = ["price", "duration", "departure"]
        if sort_by not in valid_sort_by:
            return (
                f"Error: Invalid sort_by '{sort_by}'. Must be 'price', 'duration', or 'departure'."
            )
        sort_by_value: SortBy = sort_by  # type: ignore[assignment]

        # Validate numeric parameters
        if passengers < 1:
            return "Error: Number of passengers must be at least 1."
        # H6: cap passengers at 9 (airline industry maximum per booking; prevents
        # the LLM from requesting absurd values that would fail downstream).
        if passengers > 9:
            return "Error: Number of passengers cannot exceed 9."
        if limit < 1 or limit > 20:
            return "Error: Limit must be between 1 and 20."
        if max_stops is not None and (max_stops < 0 or max_stops > 2):
            return "Error: max_stops must be 0 (direct), 1, or 2."
        if max_duration is not None and max_duration < 0:
            return "Error: max_duration must be a positive number of minutes."
        if max_price is not None and max_price <= 0:
            return "Error: max_price must be a positive number."

        # Create query
        query = FlightQuery(
            origin=origin,
            destination=destination,
            departure_date=departure_date_obj,
            passengers=passengers,
        )

        # Convert max_price to Decimal if provided
        max_price_decimal = Decimal(str(max_price)) if max_price is not None else None

        # Search flights using the client
        flights = await client.search(
            query=query,
            sort_by=sort_by_value,
            max_price=max_price_decimal,
            max_duration=max_duration,
            max_stops=max_stops,
            limit=limit,
        )

        result = _to_flight_search_result(flights, query)
        return result.model_dump_json()

    except FlightSearchError as e:
        return f"Flight search error: {e}"
    except Exception as e:
        return f"Unexpected error during flight search: {e}"
