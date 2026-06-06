"""e2e_duffel pytest config — skips suite when DUFFEL_API_TOKEN env var is absent.

Deliberately does NOT inherit the httpx autouse stub from
``tests/integration/conftest.py`` — e2e_duffel tests issue REAL HTTP traffic
to the Duffel sandbox. The root ``tests/conftest.py`` autouse fixtures
(in-memory user repo + chat collaborators) are harmless here: they patch
the FastAPI app graph but never block outbound HTTP, and these tests do
not exercise the FastAPI app.

Per D-11, the entire suite is skipped at collection time when
``DUFFEL_API_TOKEN`` is unset. The skip is enforced via a module-level
``pytestmark = pytest.mark.skipif(...)`` declared in each test file
(conftest variables are not visible to test modules without an explicit
import, so the gate must live next to the tests it guards).
"""

from __future__ import annotations

import os

import pytest

from app.flights.duffel_client import DuffelFlightClient

DUFFEL_AVAILABLE = bool(os.environ.get("DUFFEL_API_TOKEN"))


@pytest.fixture(scope="module")
def duffel_client() -> DuffelFlightClient:
    """Real :class:`DuffelFlightClient` against the Duffel sandbox.

    Module-scoped so the four tests share a single client instance — the
    HTTP layer (pyreqwest) is stateless beyond the bearer token, but reusing
    one client per module mirrors the prior Amadeus suite shape and keeps
    test wiring uniform across the gated-suite pattern (S5).
    """
    return DuffelFlightClient(
        api_token=os.environ["DUFFEL_API_TOKEN"],
        base_url="https://api.duffel.com",
    )
