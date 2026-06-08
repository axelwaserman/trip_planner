"""e2e_duffel pytest config — skips suite when no Duffel bearer token is configured.

Deliberately does NOT inherit the httpx autouse stub from
``tests/integration/conftest.py`` — e2e_duffel tests issue REAL HTTP traffic
to the Duffel sandbox. The root ``tests/conftest.py`` autouse fixtures
(in-memory user repo + chat collaborators) are harmless here: they patch
the FastAPI app graph but never block outbound HTTP, and these tests do
not exercise the FastAPI app.

Per D-11, the entire suite is skipped at collection time when no token is
available. The skip is enforced via a module-level
``pytestmark = pytest.mark.skipif(...)`` declared in each test file
(conftest variables are not visible to test modules without an explicit
import, so the gate must live next to the tests it guards).

Token resolution: ``os.environ["DUFFEL_API_TOKEN"]`` first, then
:class:`Settings` (which reads ``.env`` via pydantic-settings). pytest does
not auto-load ``.env``, so a token configured only in ``backend/.env`` would
otherwise mis-skip the suite.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import Settings
from app.flights.duffel_client import DuffelFlightClient


def _resolve_duffel_token() -> str | None:
    """Return the Duffel bearer token from os.environ, ``backend/.env``, or repo-root ``.env``.

    pytest does not auto-load ``.env``. Settings's default ``env_file=".env"``
    resolves against pytest's cwd (typically ``backend/``), but the project
    convention is one ``.env`` at the repo root. We probe both locations so
    the suite picks up a token from either checkout layout.
    """
    raw = os.environ.get("DUFFEL_API_TOKEN")
    if raw:
        return raw

    # Settings instances are cheap; we override env_file per probe.
    backend_env = Path(__file__).resolve().parents[2] / ".env"
    repo_root_env = Path(__file__).resolve().parents[3] / ".env"
    for candidate in (backend_env, repo_root_env):
        if not candidate.is_file():
            continue
        secret = Settings(_env_file=str(candidate)).duffel_api_token  # type: ignore[call-arg]
        if secret is None:
            continue
        value = secret.get_secret_value()
        if value:
            return value
    return None


_DUFFEL_TOKEN = _resolve_duffel_token()
DUFFEL_AVAILABLE = _DUFFEL_TOKEN is not None


@pytest.fixture(scope="module")
def duffel_client() -> DuffelFlightClient:
    """Real :class:`DuffelFlightClient` against the Duffel sandbox.

    Module-scoped so the four tests share a single client instance — the
    HTTP layer (pyreqwest) is stateless beyond the bearer token, but reusing
    one client per module mirrors the prior Amadeus suite shape and keeps
    test wiring uniform across the gated-suite pattern (S5).
    """
    if _DUFFEL_TOKEN is None:
        pytest.skip("DUFFEL_API_TOKEN not available (env or backend/.env)")
    return DuffelFlightClient(
        api_token=_DUFFEL_TOKEN,
        base_url="https://api.duffel.com",
    )
