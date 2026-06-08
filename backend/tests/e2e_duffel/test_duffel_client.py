"""Real-API Duffel tests (D-12). Module-level pytestmark gates collection.

Path-isolated under ``backend/tests/e2e_duffel/`` so default ``pytest`` and
the ``test`` / ``test-unit`` / ``test-integration`` / ``test-e2e``
justfile targets do NOT collect this module against the live API. Use
``just test-duffel`` (Plan 07-04 adds it) to drive the suite.

Asserts the four D-12 behaviours:
    (a) auth probe — ``_auth_probe()`` returns ``True`` against a valid token
        via the lightweight ``GET /air/airlines?limit=1`` reference endpoint
        (no offer-request quota burn).
    (b) live MAD→BCN search returns ``>= 1`` offer 30 days out. Pitfall 1:
        if the sandbox is sparse for this route, switch the test to
        ``LON`` → ``NYC`` manually — there is no auto-switch.
    (c) full vendor-neutral :class:`Flight` shape after ``_normalize_offer``:
        non-empty id, IATA origin, positive Decimal price, 3-char currency,
        non-empty carrier, positive duration, TZ-aware departure (D-09).
    (d) bogus token surfaces as :class:`APIClientError` with
        ``retryable=False``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.exceptions import APIClientError
from app.flights.duffel_client import DuffelFlightClient
from app.flights.models import FlightQuery

# Token resolution lives in conftest._resolve_duffel_token (env -> backend/.env -> repo-root .env).
from tests.e2e_duffel.conftest import DUFFEL_AVAILABLE

pytestmark = pytest.mark.skipif(
    not DUFFEL_AVAILABLE,
    reason="DUFFEL_API_TOKEN not set (env or .env)",
)


async def test_auth_probe(duffel_client: DuffelFlightClient) -> None:
    """D-12(a): a valid token yields a 2xx on the lightweight reference endpoint.

    RESEARCH §Code Example 4: ``GET /air/airlines?limit=1`` is reference data
    and bypasses the offer-request per-search quota. The probe is the
    cheapest possible auth verification and is exercised exclusively by
    this gated suite — ``health_check`` deliberately does NOT call it.
    """
    assert await duffel_client._auth_probe() is True


async def test_real_search_returns_results(duffel_client: DuffelFlightClient) -> None:
    """D-12(b): MAD→BCN 30 days out returns at least one offer (Pitfall 1)."""
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )
    results = await duffel_client.search(query, limit=5)
    assert len(results) >= 1


async def test_vendor_neutral_shape(duffel_client: DuffelFlightClient) -> None:
    """D-12(c): the first result satisfies the vendor-neutral Flight contract."""
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )
    results = await duffel_client.search(query, limit=5)
    first = results[0]
    assert first.id
    assert first.origin == "MAD"
    assert first.price > Decimal("0")
    assert isinstance(first.currency, str)
    assert len(first.currency) == 3
    assert first.carrier
    assert first.duration_minutes > 0
    # D-09: naive Duffel timestamps get UTC attached at normalization.
    assert first.departure.tzinfo is not None


async def test_error_mapping_401_with_bogus_token() -> None:
    """D-12(d): a bogus token surfaces as APIClientError(retryable=False).

    Constructs a fresh client with a synthetic invalid token (NOT the
    fixture-fed real token) so any leakage in trace output is harmless
    (T-07-04-01 mitigation).
    """
    bad_client = DuffelFlightClient(
        api_token="duffel_test_invalid_xxxxxxxxxxxxxxxx",
        base_url="https://api.duffel.com",
    )
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )
    with pytest.raises(APIClientError) as exc_info:
        await bad_client.search(query)
    assert exc_info.value.retryable is False
