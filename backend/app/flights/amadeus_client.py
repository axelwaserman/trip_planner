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
from typing import TYPE_CHECKING, NoReturn

import pybreaker
from pyreqwest.client import ClientBuilder

from app.exceptions import (
    APIClientError,
    APIError,
    APIRateLimitError,
    APIServerError,
    FlightSearchError,
)
from app.tools.flight_client import FlightAPIClient

if TYPE_CHECKING:
    from decimal import Decimal

    from app.flights.models import Flight, FlightQuery, SortBy

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

        Wraps any underlying exception as ``APIError(retryable=True)`` so the
        outer tenacity decorator can re-attempt (D-03). The error message
        deliberately includes only the exception class name — never the
        formatted exception text — to defend against credential echoing in
        vendor error payloads (T-07-02 / T-07-03).

        Returns:
            The freshly-issued access token string.

        Raises:
            APIError: With ``retryable=True`` for any underlying failure.
        """
        token_url = f"{self._base_url}{self._TOKEN_PATH}"
        try:
            async with ClientBuilder().timeout(timedelta(seconds=10)).build() as client:
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
        except Exception as exc:
            # T-07-02: do NOT include str(exc) — Amadeus has been observed to
            # echo client_id back in error responses; the class name is
            # sufficient to triage without leaking the secret.
            raise APIError(
                message=f"Amadeus token refresh failed: {type(exc).__name__}",
                retryable=True,
            ) from exc

        access_token: str = body["access_token"]
        expires_in: int = int(body["expires_in"])
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
        """Search Amadeus for flight offers (Task 2 implementation).

        Raises:
            NotImplementedError: Until Task 2 wires retry+breaker+pyreqwest.
        """
        raise NotImplementedError("AmadeusFlightClient.search lands in Task 2")

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
