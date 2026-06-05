"""Tests for ``AmadeusFlightClient.search`` composition + parsing edge cases.

Locks four invariants of :mod:`app.flights.amadeus_client`:

1. **Open-breaker mapping (D-13).** Once the breaker trips, subsequent calls
   surface :class:`APIServerError(retryable=False)` (so tenacity does NOT
   retry into the open breaker). The trip-causing call surfaces the
   breaker-mapped error rather than the wrapped exception.
2. **401 invalidates the token cache (T-07-04 / OQ-1).** A 401 from
   ``_search_impl`` clears ``_access_token`` and ``_expires_at`` BEFORE
   raising :class:`APIClientError`, so the next user-driven call refreshes
   the token.
3. **Naive datetimes get UTC attached (Pitfall 2).** The Phase 4.6
   ``normalize_amadeus_offer`` path now attaches UTC when ``departure.at``
   is naive, instead of constructing a TZ-naive ``FlightEndpoint``.
4. **Booking-class fallback (sandbox-permissive).** Unknown cabin codes
   fall back to ``"economy"`` rather than raising — Amadeus sandbox has been
   observed to return non-IATA strings.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pybreaker
import pytest
from pyreqwest.exceptions import StatusError

from app.exceptions import APIClientError, APIServerError
from app.flights.amadeus_client import AmadeusFlightClient
from app.flights.models import Flight, FlightQuery
from app.tools.flight_search import normalize_amadeus_offer


def _make_client() -> AmadeusFlightClient:
    """Construct an AmadeusFlightClient with throwaway sandbox base URL."""
    return AmadeusFlightClient("k", "s", "https://test.api.amadeus.com")


def _future_date() -> date:
    """Return a date safely in the future (FlightQuery rejects past dates)."""
    return (datetime.now(UTC) + timedelta(days=30)).date()


@pytest.mark.asyncio
async def test_circuit_breaker_open_raises_apiservererror_not_retried() -> None:
    """Open breaker is mapped to APIServerError(retryable=False) (D-13).

    With ``fail_max=1`` the very first ``_search_impl`` failure trips the
    breaker. The trip-causing call surfaces ``CircuitBreakerError`` from
    inside ``_handle_error`` (pybreaker semantics with
    ``throw_new_error_on_trip=True``); ``_fetch_with_retry_breaker`` catches
    it and re-raises as ``APIServerError(retryable=False)``. A subsequent
    call short-circuits via ``before_call`` and surfaces the same mapped
    error without invoking ``_search_impl`` again.
    """
    client = _make_client()
    # Force fail_max=1 so a single failure trips. Replace the instance
    # breaker; the original was created in __init__ with fail_max=5.
    client._breaker = pybreaker.CircuitBreaker(
        fail_max=1, reset_timeout=60, throw_new_error_on_trip=True
    )

    impl_mock = AsyncMock(side_effect=APIServerError(message="boom", retryable=True))
    query = FlightQuery(
        origin="LAX", destination="JFK", departure_date=_future_date(), passengers=1
    )

    # Disable retry sleeps by patching tenacity's sleep so the test runs
    # instantly even when retry_on_failure schedules waits.
    with (
        patch.object(client, "_search_impl", impl_mock),
        patch("tenacity.nap.time.sleep", return_value=None),
    ):
        with pytest.raises(APIServerError) as first_call:
            await client.search(query)
        # The trip-causing call: pybreaker masks the wrapped APIServerError
        # with CircuitBreakerError, which our wrapper maps back to
        # APIServerError(retryable=False).
        assert first_call.value.retryable is False
        assert "circuit breaker open" in first_call.value.message.lower()

        # Once open, before_call short-circuits — _search_impl is NOT
        # invoked a second time.
        with pytest.raises(APIServerError) as second_call:
            await client.search(query)
        assert second_call.value.retryable is False

    # Exactly one underlying call hit the implementation before the breaker
    # opened (the trip-causing call). Subsequent calls were short-circuited.
    assert impl_mock.await_count == 1


@pytest.mark.asyncio
async def test_search_401_invalidates_token_cache() -> None:
    """A 401 from _search_impl clears the token cache before raising.

    Drives ``_search_impl`` directly (not through ``search``) so the
    error-mapping side effect is observable without breaker/retry noise.
    Patches ``ClientBuilder`` so the GET chain raises a fake ``StatusError``
    with ``details["status"] == 401``.
    """
    client = _make_client()
    pre_expiry = datetime.now(UTC) + timedelta(hours=1)
    client._access_token = "stale"
    client._expires_at = pre_expiry

    # _get_token short-circuits to the cached value (well outside buffer);
    # verified by patching it explicitly to avoid network access in case the
    # cache logic ever changes.
    with patch.object(client, "_get_token", AsyncMock(return_value="stale")):
        # Build a fake send() that raises StatusError with status=401. The
        # builder chain is .get(url).bearer_auth(token).query(params).build().send().
        fake_status = StatusError("auth failed", {"status": 401, "causes": []})

        async def fake_send() -> object:
            raise fake_status

        # Construct a chain of MagicMocks that mirror the pyreqwest builder API.
        with patch("app.flights.amadeus_client.ClientBuilder") as cb_cls:
            client_builder = cb_cls.return_value
            client_builder.timeout.return_value = client_builder
            client_builder.error_for_status.return_value = client_builder

            class _FakeClient:
                async def __aenter__(self) -> "_FakeClient":
                    return self

                async def __aexit__(self, *_args: object) -> None:
                    return None

                def get(self, _url: str) -> "_FakeRequestBuilder":
                    return _FakeRequestBuilder()

            class _FakeRequestBuilder:
                def bearer_auth(self, _token: str) -> "_FakeRequestBuilder":
                    return self

                def query(self, _params: dict[str, str]) -> "_FakeRequestBuilder":
                    return self

                def build(self) -> "_FakeRequest":
                    return _FakeRequest()

            class _FakeRequest:
                async def send(self) -> object:
                    raise fake_status

            client_builder.build.return_value = _FakeClient()

            query = FlightQuery(
                origin="LAX",
                destination="JFK",
                departure_date=_future_date(),
                passengers=1,
            )
            with pytest.raises(APIClientError) as exc_info:
                await client._search_impl(query, 5, 0)

    assert exc_info.value.retryable is False
    # Cache invalidated: the next user-driven retry will refresh the token.
    assert client._access_token is None
    assert client._expires_at == datetime.min.replace(tzinfo=UTC)


def test_naive_datetime_normalized_to_utc() -> None:
    """normalize_amadeus_offer attaches UTC when departure.at is naive (Pitfall 2)."""
    offer = {
        "id": "OFFER-001",
        "itineraries": [
            {
                "duration": "PT1H30M",
                "segments": [
                    {
                        "id": "SEG-1",
                        "carrierCode": "AB",
                        "number": "100",
                        "duration": "PT1H30M",
                        # Naive ISO datetime (no TZ offset) — the Pitfall 2
                        # path under test.
                        "departure": {"iataCode": "MAD", "at": "2024-11-01T08:00:00"},
                        "arrival": {"iataCode": "BCN", "at": "2024-11-01T09:30:00"},
                    }
                ],
            }
        ],
        "price": {"total": "199.99", "currency": "USD"},
        "travelerPricings": [
            {"fareDetailsBySegment": [{"cabin": "ECONOMY"}]}
        ],
    }
    dictionaries = {
        "carriers": {"AB": "Test Carrier"},
        "locations": {"MAD": {"cityCode": "MAD"}, "BCN": {"cityCode": "BCN"}},
    }

    result = normalize_amadeus_offer(offer, dictionaries)

    assert len(result.segments) == 1
    seg = result.segments[0]
    # UTC was attached as a fallback — both endpoints are now TZ-aware.
    assert seg.departure.at.tzinfo is not None
    assert seg.departure.at.tzinfo == UTC
    assert seg.arrival.at.tzinfo is not None
    assert seg.arrival.at.tzinfo == UTC


def test_unknown_cabin_falls_back_to_economy() -> None:
    """Unknown cabin codes log a warning and fall back to 'economy' (sandbox-permissive)."""
    # Direct unit test of the static helper — avoids constructing a full
    # Amadeus offer + going through search.
    weird_offer = {
        "travelerPricings": [
            {"fareDetailsBySegment": [{"cabin": "MYSTERY_CABIN"}]}
        ]
    }
    assert AmadeusFlightClient._extract_booking_class(weird_offer) == "economy"

    # Known codes round-trip lowercase.
    assert (
        AmadeusFlightClient._extract_booking_class(
            {"travelerPricings": [{"fareDetailsBySegment": [{"cabin": "BUSINESS"}]}]}
        )
        == "business"
    )
    # Missing fields fall back gracefully (no IndexError).
    assert AmadeusFlightClient._extract_booking_class({}) == "economy"


@pytest.mark.asyncio
async def test_search_offset_returns_correct_slice() -> None:
    """``search(limit=2, offset=2)`` returns the third + fourth flights (CR-01).

    Regression test for the pre-fix double-application bug: pre-Task-1
    code requested ``max=str(limit)`` from Amadeus AND sliced
    ``[offset : offset + limit]`` post-fetch, so any ``offset > 0``
    silently produced wrong/empty results because the underlying fetch
    only returned ``limit`` items, none of which sat past index ``offset``.

    Strategy: stub ``_search_impl`` to return four flights regardless of
    args (the stub stands in for what an over-fetching Amadeus call would
    yield under Path A). With ``sort_by="departure"`` and monotonically
    increasing departures the post-sort order matches the stub's insertion
    order, so the slice ``[2:4]`` must yield ``["F2", "F3"]``.
    """
    client = _make_client()
    base_dt = datetime.now(UTC) + timedelta(days=30)
    flights = [
        Flight(
            id=f"F{i}",
            origin="LAX",
            destination="JFK",
            departure=base_dt + timedelta(hours=i),
            arrival=base_dt + timedelta(hours=i + 5),
            price=Decimal("100"),
            currency="USD",
            carrier="Test Carrier",
            flight_number=f"TT{100 + i}",
            duration_minutes=300,
            stops=0,
            booking_class="economy",
        )
        for i in range(4)
    ]

    impl_mock = AsyncMock(return_value=flights)
    query = FlightQuery(
        origin="LAX",
        destination="JFK",
        departure_date=_future_date(),
        passengers=1,
    )

    with (
        patch.object(client, "_search_impl", impl_mock),
        patch("tenacity.nap.time.sleep", return_value=None),
    ):
        result = await client.search(query, sort_by="departure", limit=2, offset=2)

    # Path A semantics: the slice [offset : offset + limit] of the
    # filtered+sorted four-flight list yields exactly F2 and F3.
    assert [f.id for f in result] == ["F2", "F3"]
    # No retry loop fired — the stub returns successfully on the first call.
    assert impl_mock.await_count == 1
    # Path A also forwards limit + offset = 4 down into _search_impl.
    call_args = impl_mock.await_args
    assert call_args is not None
    # _fetch_with_retry_breaker invokes _search_impl as
    # ``self._search_impl(query, limit, offset)`` via ``call_with_breaker``.
    forwarded_args = call_args.args
    # call_with_breaker forwards ``(query, limit, offset)`` positionally.
    assert forwarded_args[1] == 2  # limit unchanged
    assert forwarded_args[2] == 2  # offset preserved through the chain
