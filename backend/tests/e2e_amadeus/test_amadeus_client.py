"""Real-API Amadeus client tests (D-15).

Gated by a module-level ``pytestmark`` skipif so the entire suite is skipped
atomically when ``AMADEUS_API_KEY`` or ``AMADEUS_API_SECRET`` is absent.
Path-isolated under ``backend/tests/e2e_amadeus/`` so default ``pytest`` and
the ``test``/``test-unit``/``test-integration``/``test-e2e`` justfile targets
do NOT collect this module (D-14).

Asserts the four D-15 behaviours:

* token fetch + cache hit (two ``_get_token()`` calls, single network round-trip);
* real ``MAD→BCN`` search returns ≥ 1 result (Pitfall 1 — sandbox-reliable route);
* vendor-neutral ``Flight`` shape after normalisation;
* error mapping for bad credentials (401 surfaces from ``_refresh_token`` as
  :class:`APIClientError(retryable=False)` via the new ``StatusError`` branch
  added in Plan 07-07 — D-11 end-to-end).
"""

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.exceptions import APIClientError
from app.flights.amadeus_client import AmadeusFlightClient
from app.flights.models import FlightQuery

AMADEUS_AVAILABLE = bool(os.environ.get("AMADEUS_API_KEY")) and bool(os.environ.get("AMADEUS_API_SECRET"))

# Module-level skip — atomic per D-14. Conftest module variables are not
# automatically visible inside test modules, so the predicate is restated here.
pytestmark = pytest.mark.skipif(
    not AMADEUS_AVAILABLE,
    reason="AMADEUS_API_KEY and AMADEUS_API_SECRET not set",
)


@pytest.mark.asyncio
async def test_token_fetch_and_cache(amadeus_client: AmadeusFlightClient) -> None:
    """Two sequential ``_get_token`` calls return the same cached token.

    The first call performs the OAuth2 client_credentials POST; the second
    must short-circuit on the in-process cache (D-01). After the first call
    the bearer token is set and ``_expires_at`` is in the future.
    """
    token1 = await amadeus_client._get_token()
    token2 = await amadeus_client._get_token()

    assert isinstance(token1, str) and token1
    assert token1 == token2
    # The cache slot is populated and the expiry is in the future.
    assert amadeus_client._access_token == token1
    assert amadeus_client._expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_real_search_returns_results(amadeus_client: AmadeusFlightClient) -> None:
    """``MAD→BCN`` 30-days-out returns at least one offer (Pitfall 1).

    The Madrid→Barcelona route is reliably populated in the Amadeus test
    sandbox; the date is held a month out so the request stays valid against
    the sandbox's time-bounded inventory. Asserts ``>= 1`` (never ``== N``)
    per Pitfall 1.
    """
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )

    results = await amadeus_client.search(query, limit=5)

    assert len(results) >= 1


@pytest.mark.asyncio
async def test_vendor_neutral_shape(amadeus_client: AmadeusFlightClient) -> None:
    """First result satisfies the vendor-neutral ``Flight`` contract (D-15).

    Asserts the populated shape after normalisation: identifier, origin
    matches the query, price is positive, currency is a 3-letter ISO code,
    carrier name is non-empty, duration is positive minutes.
    """
    query = FlightQuery(
        origin="MAD",
        destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )

    results = await amadeus_client.search(query, limit=5)

    assert len(results) >= 1
    first = results[0]
    assert first.id
    assert first.origin == "MAD"
    assert first.price > Decimal("0")
    assert isinstance(first.currency, str) and len(first.currency) == 3
    assert first.carrier
    assert first.duration_minutes > 0


@pytest.mark.asyncio
async def test_error_mapping_401_with_bad_credentials() -> None:
    """Bad credentials surface as ``APIClientError(retryable=False)`` from ``_refresh_token`` (D-11).

    Post-Plan-07-07 contract: ``error_for_status(True)`` on the OAuth POST
    + the explicit ``except StatusError`` branch routes the 401 through
    ``_raise_from_http_status`` -> ``APIClientError(retryable=False)``.
    Previously the assertion was the broader ``APIError``, which matched
    the buggy ``APIError(retryable=True)`` from the catch-all wrap and so
    regression-locked the bug instead of the contract. The tighter
    ``APIClientError`` + ``retryable is False`` pair locks the contract:
    tenacity must NOT retry against bad credentials (T-07-04 mitigation),
    and the message-scrubbing rationale (T-07-02 / T-07-03 — never echo
    ``str(exc)``) is preserved by ``_raise_from_http_status`` constructing
    messages from ``status`` only.
    """
    bad_client = AmadeusFlightClient(
        api_key="wrong",
        api_secret="wrong",
        base_url="https://test.api.amadeus.com",
    )

    with pytest.raises(APIClientError) as exc_info:
        await bad_client._get_token()
    assert exc_info.value.retryable is False
