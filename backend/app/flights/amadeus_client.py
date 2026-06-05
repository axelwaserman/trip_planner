"""Amadeus REST flight API client (Phase 7 — REQ-real-flight-api).

Implements :class:`app.tools.flight_client.FlightAPIClient` against the Amadeus
``v2/shopping/flight-offers`` endpoint with:

* OAuth2 client_credentials token fetch (``/v1/security/oauth2/token``) with an
  in-process token cache, proactive refresh inside a 60-second buffer, and an
  ``asyncio.Lock`` instance variable so concurrent ``_get_token()`` callers
  trigger exactly one underlying refresh (D-01, D-02; 07-RESEARCH.md Pattern 1
  / Pitfall 7).
* Composition order ``@retry_on_failure`` (Plan 01 tenacity wrapper) outside,
  ``call_with_breaker`` (Plan 03 pybreaker helper) inside,
  ``_search_impl`` (pyreqwest GET) innermost (D-12).
* HTTP status mapping onto the existing :class:`app.exceptions.APIError`
  hierarchy (D-11): 401 / non-429 4xx → :class:`APIClientError(retryable=False)`,
  429 → :class:`APIRateLimitError(retryable=True)`, 5xx →
  :class:`APIServerError(retryable=True)`. An open breaker raises
  :class:`pybreaker.CircuitBreakerError` which is mapped to
  :class:`APIServerError(retryable=False)` so tenacity does NOT retry into
  the open breaker (D-13).

Outbound HTTP uses ``pyreqwest`` exclusively (ADR-008 / D-10) — never
``aiohttp``, ``httpx``, or ``requests``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NoReturn

import pybreaker
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, RequestTimeoutError, StatusError

from app.exceptions import (
    APIClientError,
    APIError,
    APIRateLimitError,
    APIServerError,
    APITimeoutError,
    FlightSearchError,
)
from app.flights.models import Flight
from app.tools.circuit_breaker import call_with_breaker
from app.tools.flight_client import FlightAPIClient
from app.tools.retry import retry_on_failure

if TYPE_CHECKING:
    from app.flights.models import BookingClass, FlightQuery, SortBy

logger = logging.getLogger(__name__)


# ISO 8601 PT-duration parser. Amadeus emits e.g. ``"PT2H30M"``. Hours and
# minutes are both optional ("PT45M" or "PT3H"); we sum what's present.
_PT_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?$")


def _iso_pt_to_minutes(duration: str) -> int:
    """Parse an ISO 8601 PT duration string ``"PT<H>H<M>M"`` into total minutes.

    Args:
        duration: Amadeus-style ISO 8601 duration string, e.g. ``"PT2H30M"``.

    Returns:
        Total minutes; 0 if the string does not match the PT pattern.
    """
    match = _PT_DURATION_RE.match(duration)
    if not match:
        return 0
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
    """Filter ``flights`` by inclusive max_price / max_duration / max_stops."""
    filtered = flights
    if max_price is not None:
        filtered = [f for f in filtered if f.price <= max_price]
    if max_duration is not None:
        filtered = [f for f in filtered if f.duration_minutes <= max_duration]
    if max_stops is not None:
        filtered = [f for f in filtered if f.stops <= max_stops]
    return filtered


def _sort_flights(flights: list[Flight], sort_by: SortBy) -> list[Flight]:
    """Sort ``flights`` by ``price``, ``duration``, or ``departure``."""
    if sort_by == "price":
        return sorted(flights, key=lambda f: f.price)
    if sort_by == "duration":
        return sorted(flights, key=lambda f: f.duration_minutes)
    if sort_by == "departure":
        return sorted(flights, key=lambda f: f.departure)
    return flights


def _raise_from_http_status(status: int, exc: Exception) -> NoReturn:
    """Map an Amadeus HTTP status code onto the project's :class:`APIError` hierarchy.

    D-11 mapping:

    * 401 → :class:`APIClientError(retryable=False)` — the caller is responsible
      for invalidating the token cache before invoking this helper so the next
      user-driven call refreshes the token (T-07-04).
    * Other 4xx (excluding 429) → :class:`APIClientError(retryable=False)`.
    * 429 → :class:`APIRateLimitError(retryable=True)`.
    * 5xx → :class:`APIServerError(retryable=True)`.
    * Unknown / 0 → :class:`APIServerError(retryable=True)`.

    Error messages are constructed from ``status`` only — never from response
    bodies — to defend against credential echoing in vendor error payloads
    (T-07-03).

    Args:
        status: HTTP status code from the failed Amadeus call.
        exc: Originating exception, attached via ``raise ... from exc``.

    Raises:
        APIClientError: For 4xx codes (including 401).
        APIRateLimitError: For 429.
        APIServerError: For 5xx and unknown codes.
    """
    if status == 401:
        raise APIClientError(message="Amadeus authentication failed (401)", retryable=False) from exc
    if status == 429:
        raise APIRateLimitError(message="Amadeus rate limit exceeded (429)", retryable=True) from exc
    if 400 <= status < 500:
        raise APIClientError(message=f"Amadeus client error ({status})", retryable=False) from exc
    if 500 <= status < 600:
        raise APIServerError(message=f"Amadeus server error ({status})", retryable=True) from exc
    raise APIServerError(message=f"Amadeus unknown error (status={status})", retryable=True) from exc


class AmadeusFlightClient(FlightAPIClient):
    """Concrete :class:`FlightAPIClient` backed by the Amadeus REST API.

    Token lifecycle uses an in-process cache with proactive refresh inside a
    60-second expiry buffer and a per-instance ``asyncio.Lock`` so concurrent
    callers cause exactly one refresh (D-01 / D-02; Pitfall 7).

    ``search`` composes ``@retry_on_failure`` (Plan 01) outside
    ``call_with_breaker`` (Plan 03) outside ``_search_impl`` (pyreqwest GET) —
    retry-outside / breaker-inside / HTTP-innermost (D-10 / D-12). An open
    breaker is mapped to :class:`APIServerError(retryable=False)` so tenacity
    does NOT retry into it (D-13).
    """

    _REFRESH_BUFFER_SECONDS = 60
    _TOKEN_PATH = "/v1/security/oauth2/token"
    _SEARCH_PATH = "/v2/shopping/flight-offers"

    def __init__(self, api_key: str, api_secret: str, base_url: str) -> None:
        """Construct the client without performing any network I/O.

        Args:
            api_key: Amadeus client_id (raw string; the caller is responsible
                for unwrapping ``Settings.amadeus_api_key`` via
                ``.get_secret_value()`` before passing it in).
            api_secret: Amadeus client_secret (raw string; same SecretStr
                unwrap responsibility as ``api_key``).
            base_url: Either ``https://test.api.amadeus.com`` (sandbox) or
                ``https://api.amadeus.com`` (production), selected upstream
                from ``Settings.amadeus_env``.
        """
        self._api_key = api_key
        self._api_secret = api_secret
        # Strip a trailing slash so ``f"{base_url}{path}"`` joins cleanly even
        # if the env override accidentally includes one.
        self._base_url = base_url.rstrip("/")
        self._access_token: str | None = None
        self._expires_at: datetime = datetime.min.replace(tzinfo=UTC)
        # Pitfall 7: the lock MUST be an instance variable, not a class
        # variable — a shared lock would serialize unrelated client instances
        # (e.g. test-isolated fakes) under the same critical section.
        self._token_lock = asyncio.Lock()
        # D-12 / Assumption A5: same trip thresholds as the project default.
        # ``throw_new_error_on_trip=True`` lets ``call_with_breaker`` surface
        # ``CircuitBreakerError`` rather than the wrapped exception on the
        # trip-causing call (regression-locked in test_circuit_breaker.py).
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            throw_new_error_on_trip=True,
        )

    # ------------------------------------------------------------------
    # Token cache
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Return a valid Amadeus access token, refreshing if needed.

        Implements the double-checked locking pattern (07-RESEARCH.md Pattern 1):
        a fast-path read covers the common case; the slow-path
        ``async with self._token_lock`` re-reads under the lock so concurrent
        callers do not all refresh.

        Returns:
            A non-empty bearer token string.

        Raises:
            APIError: With ``retryable=True`` when the underlying refresh fails.
        """
        now = datetime.now(UTC)
        token = self._access_token
        if token is not None and now < self._expires_at - timedelta(seconds=self._REFRESH_BUFFER_SECONDS):
            return token

        async with self._token_lock:
            # Re-check inside the lock: a concurrent caller may have just
            # refreshed while we were waiting for the mutex.
            now = datetime.now(UTC)
            token = self._access_token
            if token is not None and now < self._expires_at - timedelta(seconds=self._REFRESH_BUFFER_SECONDS):
                return token
            return await self._refresh_token()

    async def _refresh_token(self) -> str:
        """Fetch a new access token via OAuth2 client_credentials.

        Maps HTTP status, timeout, and connection errors onto the project's
        :class:`APIError` hierarchy (D-11) by mirroring the canonical
        instrumentation in :meth:`_search_impl`:

        * ``error_for_status(True)`` on the OAuth POST so non-2xx responses
          raise :class:`pyreqwest.exceptions.StatusError` instead of being
          parsed as JSON (CR-02 fix).
        * Explicit branches for :class:`StatusError`,
          :class:`RequestTimeoutError`, :class:`ConnectError` BEFORE the
          catch-all so 401 maps to :class:`APIClientError(retryable=False)`,
          429 to :class:`APIRateLimitError`, 5xx to
          :class:`APIServerError`, and timeouts/connect to
          :class:`APITimeoutError(retryable=True)`.
        * The catch-all ``except Exception`` remains as
          defense-in-depth for genuinely unexpected errors and still wraps
          as ``APIError(retryable=True)`` with the class-name-only message
          (T-07-02 / T-07-03 — never echo ``str(exc)``).
        * A focused malformed-body guard maps a 2xx response missing
          ``access_token`` / ``expires_in`` onto
          :class:`APIError(retryable=False)` — vendor protocol violations
          are not transient.

        Returns:
            The freshly-issued access token string.

        Raises:
            APIClientError: For 4xx including 401 (``retryable=False``).
            APIRateLimitError: For 429 (``retryable=True``).
            APIServerError: For 5xx (``retryable=True``).
            APITimeoutError: For timeouts and connect failures
                (``retryable=True``).
            APIError: With ``retryable=False`` for malformed 2xx bodies;
                with ``retryable=True`` from the catch-all for unexpected
                failures.
        """
        token_url = f"{self._base_url}{self._TOKEN_PATH}"
        try:
            async with (
                ClientBuilder().timeout(timedelta(seconds=10)).error_for_status(True).build() as client
            ):
                resp = (
                    await client.post(token_url)
                    .form(
                        {
                            "grant_type": "client_credentials",
                            "client_id": self._api_key,
                            "client_secret": self._api_secret,
                        }
                    )
                    .build()
                    .send()
                )
                body = await resp.json()
        except StatusError as exc:
            # Mirror _search_impl's pattern: extract the wire status from
            # exc.details and delegate to _raise_from_http_status. The
            # helper constructs messages from `status` only — never from
            # response bodies — preserving T-07-02 / T-07-03.
            status = int(exc.details.get("status", 0))
            _raise_from_http_status(status, exc)
        except RequestTimeoutError as exc:
            raise APITimeoutError(
                message="Amadeus token refresh timed out",
                retryable=True,
            ) from exc
        except ConnectError as exc:
            raise APITimeoutError(
                message="Amadeus token refresh connection failed",
                retryable=True,
            ) from exc
        except Exception as exc:
            # T-07-02: do NOT include str(exc) — Amadeus has been observed to
            # echo client_id back in error responses; the class name is
            # sufficient to triage without leaking the secret. This branch
            # only fires for genuinely unexpected exceptions (e.g. asyncio
            # cancellation framing, pyreqwest internals); HTTP-class
            # failures are routed by the explicit branches above.
            raise APIError(
                message=f"Amadeus token refresh failed: {type(exc).__name__}",
                retryable=True,
            ) from exc

        # Malformed-body guard: a 2xx response that is missing
        # ``access_token`` / ``expires_in`` is a vendor protocol violation.
        # Surface as APIError(retryable=False) rather than letting the
        # KeyError bubble out as something callers might mistake for
        # transient (CR-02). Message is a static string — no body content
        # echoed (T-07-02 / T-07-03).
        try:
            access_token: str = body["access_token"]
            expires_in: int = int(body["expires_in"])
        except (KeyError, ValueError, TypeError) as exc:
            raise APIError(
                message="Amadeus token response malformed: missing access_token or expires_in",
                retryable=False,
            ) from exc
        self._access_token = access_token
        self._expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return access_token

    # ------------------------------------------------------------------
    # ABC stubs — Task 2 implements ``search``.
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Return ``True`` if a token can be obtained, ``False`` otherwise.

        Returns:
            ``True`` iff ``_get_token()`` succeeds. Any :class:`APIError` is
            swallowed and surfaces as ``False`` so the FastAPI healthcheck
            stays a 200 with a structured payload rather than a 5xx.
        """
        try:
            await self._get_token()
        except APIError:
            return False
        return True

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
        """Search Amadeus for flight offers, then filter / sort / paginate.

        Composition order is fixed by D-12: ``_fetch_with_retry_breaker``
        applies ``@retry_on_failure`` (Plan 01) on the outside,
        ``call_with_breaker`` (Plan 03) inside, and the pyreqwest GET
        innermost. Each retry attempt therefore re-checks the breaker
        (retry-outside, breaker-inside, HTTP-innermost).

        An open breaker (``pybreaker.CircuitBreakerError``) is mapped to
        :class:`APIServerError(retryable=False)` so tenacity's
        ``retry_if_exception`` predicate (which gates on
        ``isinstance(exc, exceptions) and getattr(exc, "retryable", False)``)
        does NOT retry into the open breaker (D-13).

        Args:
            query: Validated :class:`FlightQuery`.
            sort_by: ``"price"`` (default), ``"duration"``, or ``"departure"``.
            max_price: Inclusive upper bound on price (Decimal).
            max_duration: Inclusive upper bound on total duration (minutes).
            max_stops: Inclusive upper bound on the number of stops.
            limit: Maximum number of offers to return.
            offset: Pagination offset. Folded into ``_search_impl``'s
                Amadeus ``max`` parameter as ``limit + offset`` so the
                post-fetch slice ``[offset : offset + limit]`` is
                well-formed (CR-01). Amadeus exposes no native numeric
                offset; over-fetching + slicing is the documented
                workaround.

        Returns:
            A list of :class:`Flight` objects matching the criteria, sorted
            and sliced. Empty list when Amadeus returns no offers.
        """
        flights = await self._fetch_with_retry_breaker(query, limit, offset)
        flights = _apply_filters(flights, max_price, max_duration, max_stops)
        flights = _sort_flights(flights, sort_by)
        return flights[offset : offset + limit]

    @retry_on_failure(max_retries=3, backoff_base=2.0)
    async def _fetch_with_retry_breaker(
        self, query: FlightQuery, limit: int, offset: int
    ) -> list[Flight]:
        """Run ``_search_impl`` under retry+breaker composition (D-12 / D-13).

        The decorator order is structural — ``@retry_on_failure`` decorates
        this private method, and the body invokes ``call_with_breaker``
        wrapping ``_search_impl``. Mapping ``CircuitBreakerError`` ->
        ``APIServerError(retryable=False)`` happens here so tenacity's
        ``retry_if_exception`` predicate sees ``retryable=False`` and skips
        retries into the open breaker (D-13).
        """
        try:
            return await call_with_breaker(
                self._breaker,
                self._search_impl,
                query,
                limit,
                offset,
            )
        except pybreaker.CircuitBreakerError as exc:
            raise APIServerError(
                message="Amadeus circuit breaker open",
                retryable=False,
            ) from exc

    async def _search_impl(self, query: FlightQuery, limit: int, offset: int) -> list[Flight]:
        """Inner Amadeus search call: pyreqwest GET + status mapping + parse.

        On HTTP 401 the token cache is invalidated *before* raising so the
        next user-driven retry refreshes the token (OQ-1 / T-07-04). The 401
        itself is mapped to :class:`APIClientError(retryable=False)` so
        tenacity does not auto-loop on a stale token.

        Args:
            query: Validated :class:`FlightQuery`.
            limit: Forwarded into the Amadeus ``max`` parameter as
                ``limit + offset`` (see ``offset`` below) so the post-fetch
                slice in :meth:`search` is well-formed.
            offset: Folded into the Amadeus ``max`` parameter as
                ``limit + offset`` — Amadeus has no native numeric offset,
                so we over-fetch and let :meth:`search` slice
                ``[offset : offset + limit]`` from the filtered/sorted list.
                Passing ``offset`` through here ensures we request enough
                offers to satisfy the slice; otherwise pages past the first
                would silently return empty (CR-01).

        Returns:
            Parsed :class:`Flight` list (unfiltered/unsorted/unpaginated).

        Raises:
            APIClientError: For 401 / non-429 4xx responses.
            APIRateLimitError: For 429 responses.
            APIServerError: For 5xx responses.
            APITimeoutError: For timeouts and connection failures.
        """
        token = await self._get_token()
        search_url = f"{self._base_url}{self._SEARCH_PATH}"
        params: dict[str, str] = {
            "originLocationCode": query.origin,
            "destinationLocationCode": query.destination,
            "departureDate": str(query.departure_date),
            "adults": str(query.passengers),
            # CR-01: request limit+offset so the post-fetch slice in
            # ``search()`` is well-formed. Amadeus has no native numeric
            # offset; over-fetching is the documented workaround.
            "max": str(limit + offset),
            "currencyCode": "USD",
        }
        try:
            async with (
                ClientBuilder().timeout(timedelta(seconds=15)).error_for_status(True).build() as client
            ):
                resp = (
                    await client.get(search_url)
                    .bearer_auth(token)
                    .query(params)
                    .build()
                    .send()
                )
                body: dict[str, Any] = await resp.json()
        except StatusError as exc:
            status = int(exc.details.get("status", 0))
            if status == 401:
                # OQ-1: invalidate the cache BEFORE raising so the next
                # user-driven call refreshes the token. The 401 itself is
                # not retryable (T-07-04 caps the loop at one refresh per
                # user-driven call).
                self._access_token = None
                self._expires_at = datetime.min.replace(tzinfo=UTC)
            _raise_from_http_status(status, exc)
        except RequestTimeoutError as exc:
            raise APITimeoutError(
                message="Amadeus request timed out",
                retryable=True,
            ) from exc
        except ConnectError as exc:
            raise APITimeoutError(
                message="Amadeus connection failed",
                retryable=True,
            ) from exc

        return self._parse_flight_offers(body)

    def _parse_flight_offers(self, body: dict[str, Any]) -> list[Flight]:
        """Convert an Amadeus ``flight-offers`` response body to a ``list[Flight]``.

        Constructs :class:`Flight` directly from the offer dictionaries (rather
        than going through :func:`normalize_amadeus_offer`, which produces the
        richer :class:`FlightResult`). This keeps the ABC return type intact
        and avoids a Pydantic round-trip.

        Naive ``departure.at`` / ``arrival.at`` values get UTC attached
        (Pitfall 2). Unknown cabin codes fall back to ``"economy"`` with a
        ``logger.warning`` rather than raising — Amadeus sandbox has been
        observed to surface non-IATA cabin strings.

        Args:
            body: Parsed Amadeus ``flight-offers`` JSON body.

        Returns:
            List of constructed :class:`Flight` objects (may be empty).
        """
        offers = body.get("data", [])
        carriers_dict: dict[str, str] = body.get("dictionaries", {}).get("carriers", {})
        flights: list[Flight] = []
        for offer in offers:
            itinerary = offer["itineraries"][0]
            segments = itinerary["segments"]
            first_seg = segments[0]
            last_seg = segments[-1]

            dep_at_str: str = first_seg["departure"]["at"]
            arr_at_str: str = last_seg["arrival"]["at"]
            dep_at = datetime.fromisoformat(dep_at_str)
            arr_at = datetime.fromisoformat(arr_at_str)
            # Pitfall 2: Amadeus returns naive local datetimes — attach UTC
            # as a safe fallback. Phase 8 will resolve airport-local TZ.
            if dep_at.tzinfo is None:
                dep_at = dep_at.replace(tzinfo=UTC)
            if arr_at.tzinfo is None:
                arr_at = arr_at.replace(tzinfo=UTC)

            carrier_code: str = first_seg["carrierCode"]
            carrier_name: str = carriers_dict.get(carrier_code, carrier_code)
            flight_number = f"{carrier_code}{first_seg['number']}"

            duration_minutes = _iso_pt_to_minutes(itinerary["duration"])
            stops = len(segments) - 1

            booking_class = self._extract_booking_class(offer)

            flight = Flight(
                id=offer["id"],
                origin=first_seg["departure"]["iataCode"],
                destination=last_seg["arrival"]["iataCode"],
                departure=dep_at,
                arrival=arr_at,
                price=Decimal(str(offer["price"]["total"])),
                currency=offer["price"]["currency"],
                carrier=carrier_name,
                flight_number=flight_number,
                duration_minutes=duration_minutes,
                stops=stops,
                booking_class=booking_class,
            )
            flights.append(flight)
        return flights

    @staticmethod
    def _extract_booking_class(offer: dict[str, Any]) -> BookingClass:
        """Extract a normalized booking class string from an Amadeus offer.

        Amadeus exposes the cabin code at
        ``travelerPricings[0].fareDetailsBySegment[0].cabin``. The codes
        follow IATA conventions (``ECONOMY`` / ``PREMIUM_ECONOMY`` /
        ``BUSINESS`` / ``FIRST``); we lowercase them to satisfy the project's
        :data:`BookingClass` literal. Unknown values are logged and fall back
        to ``"economy"`` rather than raising — sandbox responses occasionally
        surface non-IATA strings.

        Args:
            offer: A single Amadeus ``FlightOffer`` dict.

        Returns:
            Lowercase cabin code; ``"economy"`` on missing or unknown values.
        """
        try:
            cabin: str = offer["travelerPricings"][0]["fareDetailsBySegment"][0]["cabin"]
        except (KeyError, IndexError):
            return "economy"
        normalized = cabin.lower()
        if normalized == "economy":
            return "economy"
        if normalized == "premium_economy":
            return "premium_economy"
        if normalized == "business":
            return "business"
        if normalized == "first":
            return "first"
        logger.warning(
            "Unknown Amadeus cabin code %r; falling back to 'economy'", cabin
        )
        return "economy"

    async def get_flight_details(self, flight_id: str) -> Flight:
        """Get detailed information for a specific Amadeus offer.

        Amadeus exposes a separate ``/v2/shopping/flight-offers/pricing``
        endpoint for offer pricing and a ``/v2/schedule/flights`` endpoint
        for schedule lookup. CONTEXT.md scopes ``REQ-real-flight-api`` to the
        ``search`` path only; this method is deferred to a future plan.

        Args:
            flight_id: Offer identifier returned by ``search``.

        Raises:
            FlightSearchError: Always, in v1.
        """
        raise FlightSearchError(
            f"Flight {flight_id} not found (Amadeus get_flight_details deferred — REQ-real-flight-api covers search only)"
        )

    async def check_availability(self, flight_id: str) -> bool:
        """Return availability for ``flight_id``.

        Amadeus does not expose a per-offer availability check distinct from
        re-running search; v1 returns ``True`` so the chat layer can complete
        a flow without spurious "unavailable" branching. A future plan can
        wire ``/v2/shopping/flight-offers/pricing`` here.

        Args:
            flight_id: Offer identifier returned by ``search``.

        Returns:
            ``True`` always (v1 contract).
        """
        _ = flight_id  # explicitly unused in v1
        return True
