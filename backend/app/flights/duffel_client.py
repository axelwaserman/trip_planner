"""Duffel REST flight API client (Phase 7 — REQ-real-flight-api).

Implements :class:`app.tools.flight_client.FlightAPIClient` against Duffel's
``POST /air/offer_requests?return_offers=true`` endpoint with:

* Static bearer-token auth (no OAuth2 client_credentials, no token cache).
* Composition order ``@retry_on_failure`` outside, ``call_with_breaker``
  inside, ``_search_impl`` (pyreqwest POST) innermost (D-12-class).
* HTTP status mapping onto :class:`app.exceptions.APIError` hierarchy (D-04):
  401/422 → APIClientError(retryable=False); 429 → APIRateLimitError;
  5xx → APIServerError(retryable=True). Messages are derived from the status
  integer ONLY — never from the response body — to defend against credential
  / PII echoing in vendor error payloads (T-07-02 / Pitfall 3).
* Naive Duffel ISO timestamps get UTC attached at normalization (D-09 /
  Pitfall 2).

Outbound HTTP uses ``pyreqwest`` exclusively (ADR-008) — never aiohttp,
httpx, or requests.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NoReturn, cast

import pybreaker
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, RequestTimeoutError, StatusError

from app.exceptions import (
    APIClientError,
    APIRateLimitError,
    APIServerError,
    APITimeoutError,
)
from app.flights.models import Flight
from app.tools.circuit_breaker import call_with_breaker
from app.tools.flight_client import FlightAPIClient
from app.tools.retry import retry_on_failure

if TYPE_CHECKING:
    from app.flights.models import BookingClass, FlightQuery, SortBy

logger = logging.getLogger(__name__)

# D-03: Duffel wire-version constant. Bumping this is a code change, not a
# config change — kept as a module constant per CLAUDE.md carve-out for
# wire-version contract values (StrEnum / Settings rules do not apply).
_DUFFEL_VERSION = "v2"

# Parses Duffel ``slices[].duration`` strings of the form ``"PT1H30M"``.
_PT_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?$")


def _iso_pt_to_minutes(s: str) -> int:
    """Convert an ISO 8601 ``PT<H>H<M>M`` duration string to minutes.

    Args:
        s: Duration string like ``"PT4H15M"`` or ``"PT45M"`` or ``"PT2H"``.

    Returns:
        Total duration in whole minutes.

    Raises:
        ValueError: If ``s`` does not match the ``PT<H>H<M>M`` shape.
    """
    match = _PT_DURATION_RE.match(s)
    if match is None:
        raise ValueError(f"Invalid PT duration: {s!r}")
    hours_s, minutes_s = match.group(1), match.group(2)
    hours = int(hours_s) if hours_s else 0
    minutes = int(minutes_s) if minutes_s else 0
    return hours * 60 + minutes


def _apply_filters(
    flights: list[Flight],
    max_price: Decimal | None,
    max_duration: int | None,
    max_stops: int | None,
) -> list[Flight]:
    """Apply vendor-neutral post-fetch filters.

    Each filter is applied only when its argument is not ``None`` so the
    caller's "no constraint" intent is preserved.
    """
    filtered = flights
    if max_price is not None:
        filtered = [f for f in filtered if f.price <= max_price]
    if max_duration is not None:
        filtered = [f for f in filtered if f.duration_minutes <= max_duration]
    if max_stops is not None:
        filtered = [f for f in filtered if f.stops <= max_stops]
    return filtered


def _sort_flights(flights: list[Flight], sort_by: SortBy) -> list[Flight]:
    """Sort flights by the requested criterion (vendor-neutral)."""
    if sort_by == "price":
        return sorted(flights, key=lambda f: f.price)
    if sort_by == "duration":
        return sorted(flights, key=lambda f: f.duration_minutes)
    if sort_by == "departure":
        return sorted(flights, key=lambda f: f.departure)
    return flights


def _raise_from_http_status(status: int, exc: Exception) -> NoReturn:
    """Map a Duffel HTTP status code onto the project's APIError hierarchy.

    D-04 mapping:
      * 401 → :class:`APIClientError` (retryable=False)
      * 422 → :class:`APIClientError` (retryable=False) — Duffel validation
      * 429 → :class:`APIRateLimitError` (retryable=True)
      * other 4xx → :class:`APIClientError` (retryable=False)
      * 5xx → :class:`APIServerError` (retryable=True)
      * unknown → :class:`APIServerError` (retryable=True)

    Messages are constructed from ``status`` only — never from response
    body — to defend against credential / PII echoing in vendor error
    payloads (T-07-02 / Pitfall 3). Each branch chains via ``from exc`` so
    the original cause survives in ``__cause__``.

    Args:
        status: HTTP status code from the Duffel response.
        exc: Original exception (typically :class:`StatusError`) to chain.

    Raises:
        APIClientError: For 401, 422, and other 4xx codes (non-retryable).
        APIRateLimitError: For 429 (retryable).
        APIServerError: For 5xx and unknown codes (retryable).
    """
    if status == 401:
        raise APIClientError(message="Duffel authentication failed (401)", retryable=False) from exc
    if status == 422:
        raise APIClientError(message="Duffel validation error (422)", retryable=False) from exc
    if status == 429:
        # RESEARCH OQ-2: defer Retry-After header parsing to Phase 8; default
        # to 60s (APIRateLimitError dataclass default) for v1.
        raise APIRateLimitError(
            message="Duffel rate limit exceeded (429)",
            retryable=True,
            retry_after=60,
        ) from exc
    if 400 <= status < 500:
        raise APIClientError(message=f"Duffel client error ({status})", retryable=False) from exc
    if 500 <= status < 600:
        raise APIServerError(message=f"Duffel server error ({status})", retryable=True) from exc
    raise APIServerError(message=f"Duffel unknown error (status={status})", retryable=True) from exc


class DuffelFlightClient(FlightAPIClient):
    """Concrete :class:`FlightAPIClient` backed by Duffel's REST API v2.

    Static bearer-token auth (no OAuth2 token cache). ``search()`` composes
    ``@retry_on_failure`` outside ``call_with_breaker`` outside
    ``_search_impl`` — same composition as the deleted Amadeus client
    (D-12-class). Open-breaker is mapped to
    :class:`APIServerError` ``retryable=False`` so tenacity short-circuits
    retries into an open circuit.

    Outbound HTTP uses ``pyreqwest`` exclusively (ADR-008).
    """

    _OFFER_REQUESTS_PATH = "/air/offer_requests"

    def __init__(self, api_token: str, base_url: str) -> None:
        """Construct the client without performing any network I/O.

        Args:
            api_token: Duffel bearer token (raw string; caller unwraps
                ``Settings.duffel_api_token`` via ``.get_secret_value()``).
            base_url: Always ``"https://api.duffel.com"`` in production
                (token prefix selects sandbox vs live). Constructor accepts
                it as a parameter for testability only — see threat model
                T-07-02-03 (SSRF accepted because lifespan injects a
                fixed string).
        """
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            throw_new_error_on_trip=True,
        )

    async def health_check(self) -> bool:
        """Return ``True`` unconditionally (no network call).

        RESEARCH OQ-1: hitting Duffel for a liveness probe is wasteful and
        burns sandbox quota; ``/health`` callers want to know that the
        client is constructed and the lifespan branch chose ``"real"``. The
        actual auth probe lives in the gated e2e_duffel suite (D-12).
        """
        return True

    def _build_offer_request_body(self, query: FlightQuery, max_stops: int | None) -> dict[str, Any]:
        """Build the Duffel ``POST /air/offer_requests`` body.

        D-07: emits one slice for one-way, two slices for round-trip.
        D-13: passengers are adult-only (``[{"type": "adult"}] * n``).
        D-14: ``slice.max_connections`` present iff ``max_stops`` is not
        None — server-side filtering reduces wire bytes.
        D-10: ``cabin_class`` is hardcoded to ``"economy"`` for v1
        (``FlightQuery`` has no cabin field yet — pass-through documented
        in CONTEXT.md).
        """
        outbound: dict[str, Any] = {
            "origin": query.origin,
            "destination": query.destination,
            "departure_date": str(query.departure_date),
        }
        if max_stops is not None:
            outbound["max_connections"] = max_stops

        slices: list[dict[str, Any]] = [outbound]
        if query.return_date is not None:  # D-07: round trip adds a return slice.
            ret: dict[str, Any] = {
                "origin": query.destination,
                "destination": query.origin,
                "departure_date": str(query.return_date),
            }
            if max_stops is not None:
                ret["max_connections"] = max_stops
            slices.append(ret)

        return {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"} for _ in range(query.passengers)],
                "cabin_class": "economy",
            }
        }

    def _normalize_offer(self, offer: dict[str, Any]) -> Flight:
        """Map a Duffel offer dict onto the vendor-neutral :class:`Flight`.

        D-08: normalization lives on the client (not in
        ``flight_search.py``). D-09: naive Duffel timestamps get UTC
        attached so downstream consumers always see TZ-aware datetimes.
        D-10: cabin lives at
        ``slices[0].segments[0].passengers[0].cabin_class``.

        Args:
            offer: Single element of ``response["data"]["offers"]``.

        Returns:
            A vendor-neutral :class:`Flight`.
        """
        slice_ = offer["slices"][0]
        segments = slice_["segments"]
        first_seg, last_seg = segments[0], segments[-1]

        dep_at = datetime.fromisoformat(first_seg["departing_at"])
        arr_at = datetime.fromisoformat(last_seg["arriving_at"])
        if dep_at.tzinfo is None:
            dep_at = dep_at.replace(tzinfo=UTC)
        if arr_at.tzinfo is None:
            arr_at = arr_at.replace(tzinfo=UTC)

        cabin_raw: str = first_seg["passengers"][0]["cabin_class"]
        carrier = first_seg["marketing_carrier"]

        return Flight(
            id=offer["id"],
            origin=first_seg["origin"]["iata_code"],
            destination=last_seg["destination"]["iata_code"],
            departure=dep_at,
            arrival=arr_at,
            # Duffel emits total_amount as a string-encoded decimal; wrap
            # in str() to defend against accidental int/float input shape.
            price=Decimal(str(offer["total_amount"])),
            currency=offer["total_currency"],
            carrier=carrier["name"],
            flight_number=f"{carrier['iata_code']}{first_seg['marketing_carrier_flight_number']}",
            duration_minutes=_iso_pt_to_minutes(slice_["duration"]),
            stops=len(segments) - 1,
            # The Flight validator (normalize_booking_class) narrows the
            # raw string onto the BookingClass Literal at construction.
            booking_class=cast("BookingClass", cabin_raw.lower()),
        )

    async def _search_impl(self, query: FlightQuery, limit: int, max_stops: int | None) -> list[Flight]:
        """Issue the actual Duffel POST and normalize the response.

        Wraps the HTTP block in ``StatusError`` / ``RequestTimeoutError`` /
        ``ConnectError`` translation onto the :class:`APIError` hierarchy
        (D-04). Uses ``error_for_status(True)`` so non-2xx responses raise
        before the JSON parser sees a body it cannot parse (CR-02-class
        regression-lock).
        """
        body = self._build_offer_request_body(query, max_stops)
        url = f"{self._base_url}{self._OFFER_REQUESTS_PATH}"
        try:
            async with ClientBuilder().timeout(timedelta(seconds=15)).error_for_status(True).build() as client:
                resp = await (
                    client.post(url)
                    .query({"return_offers": "true"})
                    .bearer_auth(self._api_token)
                    .header("Duffel-Version", _DUFFEL_VERSION)
                    .header("Accept", "application/json")
                    .body_json(body)
                    .build()
                    .send()
                )
                payload: dict[str, Any] = await resp.json()
        except StatusError as exc:
            details = getattr(exc, "details", None) or {}
            status = int(details.get("status", 0))
            _raise_from_http_status(status, exc)
        except RequestTimeoutError as exc:
            raise APITimeoutError(message="Duffel request timed out", retryable=True) from exc
        except ConnectError as exc:
            raise APITimeoutError(message="Duffel connection failed", retryable=True) from exc

        offers: list[dict[str, Any]] = payload["data"]["offers"]
        # D-06: cap at the impl boundary too — defence in depth against the
        # CR-01-class double-application bug from the prior Amadeus phase.
        return [self._normalize_offer(o) for o in offers[:limit]]

    @retry_on_failure(max_retries=3, backoff_base=2.0)
    async def _fetch_with_retry_breaker(self, query: FlightQuery, limit: int, max_stops: int | None) -> list[Flight]:
        """Compose retry (outer) + breaker (inner) + ``_search_impl`` (inner-most).

        D-12-class: open-breaker is mapped to
        :class:`APIServerError` ``retryable=False`` so the tenacity
        ``_is_retryable`` predicate skips retries into an open circuit
        (Pitfall 4). Without this remap, tenacity would burn its budget
        bouncing off the closed circuit.
        """
        try:
            return await call_with_breaker(self._breaker, self._search_impl, query, limit, max_stops)
        except pybreaker.CircuitBreakerError as exc:
            raise APIServerError(
                message="Duffel circuit breaker open",
                retryable=False,
            ) from exc

    async def search(
        self,
        query: FlightQuery,
        sort_by: SortBy = "price",
        max_price: Decimal | None = None,
        max_duration: int | None = None,
        max_stops: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Flight]:
        """Search Duffel for offers matching ``query`` and return Flights.

        D-06: ``offset`` is honored but capped — Duffel's single-round-trip
        flow does not support ``offset > 0``; we return ``offers[:limit]``
        regardless of the caller's value. This avoids the CR-01-class
        double-application bug from the prior Amadeus phase.

        Args:
            query: Vendor-neutral flight query.
            sort_by: ``"price"``, ``"duration"``, or ``"departure"``.
            max_price: Client-side filter; offers above this price are
                dropped after fetch (Duffel does not expose this filter).
            max_duration: Client-side filter on total duration (minutes).
            max_stops: Server-side filter via Duffel's
                ``slice.max_connections`` (D-14); also reapplied
                client-side for safety.
            limit: Maximum results to return.
            offset: ABC-portable parameter; ignored by Duffel
                (single-round-trip flow). Documented for the contract.

        Returns:
            Up to ``limit`` :class:`Flight` instances.
        """
        del offset  # D-06: explicitly unused; documented in docstring.
        flights = await self._fetch_with_retry_breaker(query, limit, max_stops)
        flights = _apply_filters(flights, max_price, max_duration, max_stops)
        flights = _sort_flights(flights, sort_by)
        return flights[:limit]  # D-06: cap; ignore offset.

    async def get_flight_details(self, flight_id: str) -> Flight:
        """Not implemented for Duffel v1 (out of scope per CONTEXT.md).

        The single-round-trip search flow is the only supported path —
        offer detail retrieval lands in a future phase if/when LangChain
        tool surface needs it.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Duffel get_flight_details not implemented (v1)")

    async def check_availability(self, flight_id: str) -> bool:
        """Not implemented for Duffel v1 (out of scope per CONTEXT.md).

        Availability is implicit in Duffel's offer-request flow — the
        offers list is the available set at quote time. Explicit
        re-validation lands in a future phase.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Duffel check_availability not implemented (v1)")
