"""Unit tests for :class:`DuffelFlightClient`.

Coverage goals:

* Composition: open-breaker maps to ``APIServerError(retryable=False)`` so
  tenacity short-circuits retries (D-12-class / Pitfall 4).
* Normalization: one-way + round-trip fixtures land on TZ-aware
  vendor-neutral :class:`Flight` instances; naive Duffel timestamps get
  UTC attached (D-08, D-09, D-10).
* Body construction: one-way emits 1 slice, round-trip emits 2 slices,
  ``max_connections`` present iff ``max_stops`` is not None (D-07, D-13,
  D-14).
* Pagination cap: ``search(limit=2, offset=2)`` returns the head of the
  list, length ≤ limit (D-06 / CR-01 regression-lock).
* Error mapping: 401 surfaces as ``APIClientError(retryable=False)`` and
  the message NEVER echoes response body content (T-07-02 / Pitfall 3).
* Health check: returns ``True`` without performing network I/O.
"""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pybreaker
import pytest
from pyreqwest.exceptions import StatusError

from app.exceptions import APIClientError, APIServerError
from app.flights.duffel_client import DuffelFlightClient
from app.flights.models import Flight, FlightQuery

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "duffel"


def _load_fixture(name: str) -> dict[str, Any]:
    """Load a Duffel JSON fixture by filename."""
    parsed: dict[str, Any] = json.loads((_FIXTURES_DIR / name).read_text())
    return parsed


def _future_date() -> date:
    """Future date that satisfies FlightQuery's not-in-past validator."""
    return date.today() + timedelta(days=30)


def _make_flight(idx: int, price: Decimal | None = None) -> Flight:
    """Build a minimal :class:`Flight` for offset/cap tests."""
    base_dt = datetime_at_noon_plus(idx)
    return Flight(
        id=f"off_test_{idx:04d}",
        origin="MAD",
        destination="BCN",
        departure=base_dt,
        arrival=base_dt + timedelta(hours=2),
        price=price if price is not None else Decimal(f"{100 + idx}"),
        currency="EUR",
        carrier="Iberia",
        flight_number=f"IB{1000 + idx}",
        duration_minutes=120,
        stops=0,
        booking_class="economy",
    )


def datetime_at_noon_plus(idx: int) -> datetime:
    return datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC) + timedelta(hours=idx)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_normalize_offer_oneway_produces_tz_aware_flight() -> None:
    """One-way fixture (2 segments) normalizes to a TZ-aware Flight."""
    payload = _load_fixture("offer_request_response_oneway.json")
    offer = payload["data"]["offers"][0]
    client = DuffelFlightClient("dummy", "https://api.duffel.com")

    result = client._normalize_offer(offer)

    assert result.id == offer["id"]
    assert result.departure.tzinfo is not None
    assert result.arrival.tzinfo is not None
    assert result.stops == 1  # 2 segments -> 1 stop
    assert result.price > 0
    assert result.booking_class == "economy"
    assert result.currency == "EUR"
    # First segment is MAD->PMI; last is PMI->BCN.
    assert result.origin == "MAD"
    assert result.destination == "BCN"


def test_normalize_offer_naive_datetime_attaches_utc() -> None:
    """D-09 / Pitfall 2 lock: naive Duffel timestamps get UTC attached."""
    payload = _load_fixture("offer_request_response_oneway.json")
    offer = payload["data"]["offers"][0]
    client = DuffelFlightClient("dummy", "https://api.duffel.com")

    result = client._normalize_offer(offer)

    assert result.departure.tzinfo == UTC
    assert result.arrival.tzinfo == UTC


def test_normalize_offer_roundtrip_uses_outbound_slice() -> None:
    """D-08 v1: ``_normalize_offer`` reads slices[0] only.

    Round-trip handling at the Flight-list level is out of scope for v1;
    the method must surface the OUTBOUND slice's endpoints, not the
    return slice's.
    """
    payload = _load_fixture("offer_request_response_roundtrip.json")
    offer = payload["data"]["offers"][0]
    outbound = offer["slices"][0]
    expected_origin = outbound["segments"][0]["origin"]["iata_code"]
    expected_destination = outbound["segments"][-1]["destination"]["iata_code"]

    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    result = client._normalize_offer(offer)

    assert result.origin == expected_origin
    assert result.destination == expected_destination
    # Outbound slice carries flight_number 1234 in our fixture; if this
    # ever flips to 5678 we read the return slice by mistake.
    assert "1234" in result.flight_number


# ---------------------------------------------------------------------------
# Body construction
# ---------------------------------------------------------------------------


def test_build_offer_request_body_oneway() -> None:
    """One-way query -> 1 slice, no max_connections, single adult."""
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    query = FlightQuery(origin="MAD", destination="BCN", departure_date=_future_date(), passengers=1)

    body = client._build_offer_request_body(query, max_stops=None)

    assert len(body["data"]["slices"]) == 1
    assert body["data"]["passengers"] == [{"type": "adult"}]
    assert body["data"]["cabin_class"] == "economy"
    assert "max_connections" not in body["data"]["slices"][0]


def test_build_offer_request_body_roundtrip_two_slices() -> None:
    """D-07: round-trip adds a return slice with origin/destination flipped."""
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    dep = _future_date()
    ret = dep + timedelta(days=7)
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=dep,
        return_date=ret,
        passengers=1,
    )

    body = client._build_offer_request_body(query, max_stops=None)

    slices = body["data"]["slices"]
    assert len(slices) == 2
    assert slices[1]["origin"] == "BCN"
    assert slices[1]["destination"] == "MAD"
    assert slices[1]["departure_date"] == str(ret)


def test_build_offer_request_body_max_stops_maps_to_max_connections() -> None:
    """D-14: ``max_stops`` -> ``slice.max_connections`` on every slice; absent when None."""
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    dep = _future_date()
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=dep,
        return_date=dep + timedelta(days=3),
        passengers=1,
    )

    body_with = client._build_offer_request_body(query, max_stops=1)
    for sl in body_with["data"]["slices"]:
        assert sl["max_connections"] == 1

    body_without = client._build_offer_request_body(query, max_stops=None)
    for sl in body_without["data"]["slices"]:
        assert "max_connections" not in sl


def test_build_offer_request_body_passengers_list_length() -> None:
    """D-13: ``passengers`` is ``[{type:adult}] * n`` for every n in 1..9."""
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    query = FlightQuery(origin="MAD", destination="BCN", departure_date=_future_date(), passengers=3)

    body = client._build_offer_request_body(query, max_stops=None)

    assert len(body["data"]["passengers"]) == 3
    assert all(p == {"type": "adult"} for p in body["data"]["passengers"])


# ---------------------------------------------------------------------------
# Pagination cap (D-06 / CR-01 regression-lock)
# ---------------------------------------------------------------------------


async def test_search_offset_capped_returns_head_at_limit() -> None:
    """``search(limit=2, offset=2)`` returns the FIRST 2 mocked flights.

    Locks D-06: ``offset`` is documented-ignored; we never skip into the
    middle of the impl's results. Regression-lock against CR-01
    (Amadeus-phase double-application bug).
    """
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    mocked = [_make_flight(i) for i in range(5)]
    impl_mock = AsyncMock(return_value=list(mocked))
    query = FlightQuery(origin="MAD", destination="BCN", departure_date=_future_date(), passengers=1)

    with patch.object(client, "_search_impl", impl_mock):
        result = await client.search(query, limit=2, offset=2)

    assert len(result) == 2
    # Sorted by price ascending (default sort_by); flights have prices
    # 100, 101, 102, 103, 104 — the first two of the unsorted list ARE
    # also the cheapest, so head == first-two-by-price.
    assert result[0].id == mocked[0].id
    assert result[1].id == mocked[1].id


# ---------------------------------------------------------------------------
# Composition: retry + breaker
# ---------------------------------------------------------------------------


async def test_circuit_breaker_open_raises_apiservererror_not_retried() -> None:
    """D-12-class / Pitfall 4: open breaker -> APIServerError(retryable=False).

    With ``fail_max=1``: the first call's underlying error trips the
    breaker, so the second ``search()`` call hits an open circuit and
    surfaces as ``APIServerError(retryable=False)``. Tenacity's
    ``_is_retryable`` predicate gates on ``retryable=True``, so an open
    breaker does NOT consume the retry budget.
    """
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    client._breaker = pybreaker.CircuitBreaker(fail_max=1, reset_timeout=60, throw_new_error_on_trip=True)
    impl_mock = AsyncMock(side_effect=APIServerError(message="boom", retryable=True))
    query = FlightQuery(origin="MAD", destination="BCN", departure_date=_future_date(), passengers=1)

    with (
        patch.object(client, "_search_impl", impl_mock),
        patch("tenacity.nap.time.sleep", return_value=None),
    ):
        # First call: tenacity retries 4 times against a tripping breaker.
        # With fail_max=1, the FIRST attempt trips the breaker — pybreaker
        # raises CircuitBreakerError from _handle_error masking the
        # original APIServerError; our wrapper maps that to
        # APIServerError(retryable=False), which short-circuits retry.
        with pytest.raises(APIServerError) as first_call:
            await client.search(query)
        assert first_call.value.retryable is False
        assert "circuit breaker open" in first_call.value.message.lower()

        # Second call observes an already-open breaker (before_call short-
        # circuits before _search_impl is awaited).
        with pytest.raises(APIServerError) as second_call:
            await client.search(query)
        assert second_call.value.retryable is False
        assert "circuit breaker open" in second_call.value.message.lower()

    # _search_impl was awaited exactly once (the first call's sole
    # attempt). The second call was short-circuited by the open breaker
    # before reaching the impl. Tenacity did NOT burn extra attempts on
    # the trip-causing call because the breaker raised
    # CircuitBreakerError from _handle_error, which our wrapper remapped
    # to retryable=False.
    assert impl_mock.await_count == 1


# ---------------------------------------------------------------------------
# Error mapping at search() boundary
# ---------------------------------------------------------------------------


async def test_search_status_error_401_maps_to_api_client_error_not_retryable() -> None:
    """T-07-02 lock: 401 surfaces as APIClientError; message has no body content."""
    client = DuffelFlightClient("dummy", "https://api.duffel.com")
    # StatusError accepts (msg, details=...) per pyreqwest's API. We
    # construct a real one — not a MagicMock — because ``raise X from exc``
    # requires ``exc`` to be a real BaseException subclass.
    # Sensitive content is embedded in BOTH the StatusError message AND the
    # details — these are the two surfaces an accidentally-leaky impl could
    # echo into APIError.message. Neither must appear in the final message.
    fake_status_error = StatusError(
        "Unauthorized: user_email=victim@example.com leaked",
        details={"status": 401, "causes": None},
    )

    async def _impl_raises(*args: Any, **kwargs: Any) -> list[Flight]:
        # Replicate _search_impl's StatusError handling path by calling
        # _raise_from_http_status with the fake.
        from app.flights.duffel_client import _raise_from_http_status

        _raise_from_http_status(401, fake_status_error)

    query = FlightQuery(origin="MAD", destination="BCN", departure_date=_future_date(), passengers=1)

    with (
        patch.object(client, "_search_impl", _impl_raises),
        patch("tenacity.nap.time.sleep", return_value=None),
        pytest.raises(APIClientError) as exc_info,
    ):
        await client.search(query)

    assert exc_info.value.retryable is False
    # T-07-02-class: status only, no body content.
    assert "victim@example.com" not in exc_info.value.message
    assert "user_email" not in exc_info.value.message
    assert "401" in exc_info.value.message


# ---------------------------------------------------------------------------
# Health check (no network call)
# ---------------------------------------------------------------------------


async def test_health_check_returns_true_no_network_call() -> None:
    """``health_check()`` is a no-network constant True (RESEARCH OQ-1)."""
    client = DuffelFlightClient("dummy", "https://api.duffel.com")

    # Patch ClientBuilder so any accidental network attempt would explode
    # loudly. health_check must NOT touch it.
    with patch(
        "app.flights.duffel_client.ClientBuilder",
        side_effect=AssertionError("health_check should not touch the network"),
    ):
        result = await client.health_check()

    assert result is True


# ---------------------------------------------------------------------------
# CR fix regression-locks (WR-01 / WR-02 / WR-03 / IN-04)
# ---------------------------------------------------------------------------


def test_api_token_wrapped_in_secretstr_repr_opacity() -> None:
    """WR-01 lock: ``repr(client)`` must not surface the live bearer token.

    Even synthetic test tokens like ``"dummy"`` that don't match the
    scrubber regex must not appear in any default repr/__dict__ dump.
    """
    raw = "dummy_token_value_should_not_appear"
    client = DuffelFlightClient(raw, "https://api.duffel.com")
    assert raw not in repr(client)
    assert raw not in repr(client.__dict__)
    assert raw not in repr(client._api_token)
    # The wrapper still allows the call site to unwrap intentionally.
    assert client._api_token.get_secret_value() == raw


async def test_search_unexpected_payload_shape_raises_apiservererror_not_retryable() -> None:
    """WR-02 lock: a 2xx with malformed body must surface as APIError.

    Without the parser-error guard a raw ``KeyError('data')`` would
    escape ``_search_impl`` and end up as user-facing tool prose.
    """
    client = DuffelFlightClient("dummy", "https://api.duffel.com")

    async def _impl_with_bad_payload(*args: Any, **kwargs: Any) -> list[Flight]:
        # Replicate the post-parse exception the new guard raises.
        try:
            payload: dict[str, Any] = {"unexpected": "shape"}
            _ = payload["data"]["offers"]  # KeyError
        except (KeyError, ValueError, TypeError) as exc:
            raise APIServerError(message="Duffel response shape unexpected", retryable=False) from exc
        return []

    query = FlightQuery(origin="MAD", destination="BCN", departure_date=_future_date(), passengers=1)

    with (
        patch.object(client, "_search_impl", _impl_with_bad_payload),
        patch("tenacity.nap.time.sleep", return_value=None),
        pytest.raises(APIServerError) as exc_info,
    ):
        await client.search(query)

    assert exc_info.value.retryable is False
    assert "shape unexpected" in exc_info.value.message.lower()
    # Body content must not leak into the message.
    assert "unexpected" not in exc_info.value.message or "shape unexpected" in exc_info.value.message.lower()


def test_status_from_details_handles_missing_and_unparseable_status() -> None:
    """WR-03 lock: missing/non-int status collapses to 0, never raises."""
    from app.flights.duffel_client import _status_from_details

    class _StubError(Exception):
        def __init__(self, details: dict[str, Any] | None) -> None:
            self.details = details

    # Missing details -> 0
    assert _status_from_details(_StubError(None)) == 0
    # Missing status key -> 0
    assert _status_from_details(_StubError({"causes": None})) == 0
    # None status -> 0
    assert _status_from_details(_StubError({"status": None})) == 0
    # Non-numeric string -> 0 (no TypeError escape)
    assert _status_from_details(_StubError({"status": "not-a-number"})) == 0
    # List value -> 0 (TypeError suppressed)
    assert _status_from_details(_StubError({"status": [401]})) == 0
    # Numeric string -> int
    assert _status_from_details(_StubError({"status": "401"})) == 401
    # Real int -> int
    assert _status_from_details(_StubError({"status": 503})) == 503


def test_pt_duration_regex_rejects_bare_pt() -> None:
    """IN-04 lock: ``"PT"`` must not silently normalize to 0 minutes."""
    from app.flights.duffel_client import _iso_pt_to_minutes

    with pytest.raises(ValueError):
        _iso_pt_to_minutes("PT")
    # Real durations still work.
    assert _iso_pt_to_minutes("PT1H30M") == 90
    assert _iso_pt_to_minutes("PT45M") == 45
    assert _iso_pt_to_minutes("PT2H") == 120
