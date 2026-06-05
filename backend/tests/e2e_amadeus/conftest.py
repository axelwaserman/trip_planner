"""e2e_amadeus pytest config — skips suite when AMADEUS_* env vars are absent.

This conftest deliberately does NOT inherit the httpx autouse stub from
tests/integration/conftest.py — e2e_amadeus tests issue REAL HTTP traffic to
the Amadeus sandbox.

Per D-14, the entire suite is skipped at collection time when either
``AMADEUS_API_KEY`` or ``AMADEUS_API_SECRET`` is unset. The skip is enforced
via a module-level ``pytestmark`` in each test file (conftest variables are
not visible to test modules without import).
"""

import os

import pytest

from app.flights.amadeus_client import AmadeusFlightClient

AMADEUS_AVAILABLE = bool(os.environ.get("AMADEUS_API_KEY")) and bool(os.environ.get("AMADEUS_API_SECRET"))


@pytest.fixture(scope="module")
def amadeus_client() -> AmadeusFlightClient:
    """Construct a real ``AmadeusFlightClient`` against the Amadeus test sandbox.

    The fixture is module-scoped so the OAuth2 token cache is reused across
    the four tests in the suite — exercising the cache hit path naturally.
    Per D-14, e2e_amadeus targets the sandbox only; production would require
    a separate secret-gated workflow.
    """
    return AmadeusFlightClient(
        api_key=os.environ["AMADEUS_API_KEY"],
        api_secret=os.environ["AMADEUS_API_SECRET"],
        base_url="https://test.api.amadeus.com",
    )
