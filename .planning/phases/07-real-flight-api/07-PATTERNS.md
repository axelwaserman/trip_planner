# Phase 7: Real Flight API (Duffel) - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 13 (7 new, 6 modified)
**Analogs found:** 13 / 13 (12 with strong historical/current analog; 1 partial)

**Note on history.** The Amadeus integration (Phase 7 v1) was deleted wholesale in commit `5d7499c` after the vendor cancelled self-service signups. The deleted files are the highest-quality analog for the Duffel rebuild because they shipped 25/25 verification truths and embed the regression-locks (CR-01 offset, CR-02 token-cache malformed-body, T-07-02 PII-guard) the Duffel client must inherit. Historical files are pulled with `git show 5d7499c^:<path>` (the parent of the removal commit). All other analogs are current `master`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/flights/duffel_client.py` (NEW) | service (vendor client impl behind ABC) | request-response (HTTP) | `5d7499c^:backend/app/flights/amadeus_client.py` | exact (historical) |
| `backend/app/config.py` (MODIFIED) | config | n/a | current `backend/app/config.py` (existing OpenAI/Anthropic credential fields) | exact |
| `backend/app/api/main.py::lifespan` (MODIFIED) | bootstrap / DI wiring | event-driven (lifespan startup) | current `backend/app/api/main.py` lines 49-92 (current Mock-only branch) + `5d7499c^:backend/app/api/main.py` Amadeus branch | exact (combination) |
| `backend/app/llm/log_scrubbing.py` (MODIFIED) | utility (logging filter) | transform | current `backend/app/llm/log_scrubbing.py` (`SECRET_PATTERNS` tuple) | exact |
| `backend/app/tools/flight_search.py` (MODIFIED — D-08 cleanup) | tool entry-point | request-response | current `backend/app/tools/flight_search.py` (delete `normalize_amadeus_offer` + `normalize_skyscanner_itinerary`) | exact |
| `backend/tests/unit/test_duffel_client.py` (NEW) | test (unit) | request-response (mocked) | `5d7499c^:backend/tests/unit/test_amadeus_client.py` | exact (historical) |
| `backend/tests/unit/test_duffel_error_mapping.py` (NEW) | test (unit, parametrised) | transform | `5d7499c^:backend/tests/unit/test_amadeus_error_mapping.py` | exact (historical) |
| `backend/tests/unit/test_config_duffel.py` (NEW) | test (unit) | n/a | new test file; pattern is "import Settings, assert field types" — small bespoke shape | partial (no direct `test_config.py` on master; was deleted with Amadeus) |
| `backend/tests/unit/llm/test_log_scrubbing.py` (MODIFIED — extend) | test (unit) | transform | current `backend/tests/unit/llm/test_log_scrubbing.py` | exact |
| `backend/tests/integration/test_lifespan_flight_provider.py` (NEW — rebuild) | test (integration) | event-driven (lifespan) | `5d7499c^:backend/tests/integration/test_lifespan_flight_provider.py` | exact (historical) |
| `backend/tests/integration/test_health.py` (MODIFIED) | test (integration) | request-response | current `backend/tests/integration/test_health.py` | exact |
| `backend/tests/e2e_duffel/{__init__.py, conftest.py, test_duffel_client.py}` (NEW) | test (e2e, gated) | request-response (real HTTP) | `5d7499c^:backend/tests/e2e_amadeus/{conftest.py, test_amadeus_client.py}` | exact (historical) |
| `backend/tests/fixtures/duffel/offer_request_response_{oneway,roundtrip}.json` (NEW) | test fixture | n/a | (no direct analog — fixtures are vendor-shape-specific; capture from sandbox) | partial |
| `justfile` (MODIFIED — add `test-duffel`) | config | n/a | existing `test`/`test-unit`/`test-integration` targets | exact |
| `.github/workflows/ci.yml` (MODIFIED — add `duffel-e2e` job) | config | n/a | existing `e2e:` job (lines 89-119) | exact |

## Pattern Assignments

### `backend/app/flights/duffel_client.py` (service, request-response)

**Analog:** `5d7499c^:backend/app/flights/amadeus_client.py` (637 lines historical; Duffel is ~250 lines after stripping the OAuth2 token cache).

**Module docstring + imports pattern** (lines 1-55 historical):
```python
"""Duffel REST flight API client (Phase 7 — REQ-real-flight-api).

Implements :class:`app.tools.flight_client.FlightAPIClient` against Duffel's
``POST /air/offer_requests?return_offers=true`` endpoint with:

* Static bearer-token auth (no OAuth2 client_credentials, no token cache).
* Composition order ``@retry_on_failure`` outside, ``call_with_breaker``
  inside, ``_search_impl`` (pyreqwest POST) innermost (D-12-class).
* HTTP status mapping onto :class:`app.exceptions.APIError` hierarchy (D-04):
  401/422 → APIClientError(retryable=False); 429 → APIRateLimitError;
  5xx → APIServerError(retryable=True).

Outbound HTTP uses ``pyreqwest`` exclusively (ADR-008) — never aiohttp,
httpx, or requests.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NoReturn

import pybreaker
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, RequestTimeoutError, StatusError

from app.exceptions import (
    APIClientError, APIError, APIRateLimitError, APIServerError,
    APITimeoutError, FlightSearchError,
)
from app.flights.models import Flight
from app.tools.circuit_breaker import call_with_breaker
from app.tools.flight_client import FlightAPIClient
from app.tools.retry import retry_on_failure

if TYPE_CHECKING:
    from app.flights.models import BookingClass, FlightQuery, SortBy

logger = logging.getLogger(__name__)

_DUFFEL_VERSION = "v2"  # D-03: wire-version constant per CLAUDE.md carve-out
_PT_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?$")
```

**`_iso_pt_to_minutes` helper** (lines 58-74 historical) — copy verbatim; Duffel `slices[].duration` is the same `PT<H>H<M>M` shape as Amadeus.

**`_apply_filters` + `_sort_flights` module-level helpers** (lines 77-100 historical) — copy verbatim. These are vendor-neutral and apply post-fetch.

**`_raise_from_http_status` pattern** (D-04 — lines 103-138 historical, with D-04 422 branch added):
```python
def _raise_from_http_status(status: int, exc: Exception) -> NoReturn:
    """Map a Duffel HTTP status code onto the project's APIError hierarchy.

    D-04 mapping:
      * 401 → APIClientError(retryable=False)
      * 422 → APIClientError(retryable=False)  # Duffel validation error
      * 429 → APIRateLimitError(retryable=True)
      * other 4xx → APIClientError(retryable=False)
      * 5xx → APIServerError(retryable=True)
      * unknown → APIServerError(retryable=True)

    Messages are constructed from `status` only — never from response body —
    to defend against credential / PII echoing in vendor error payloads
    (T-07-02-class mitigation; Pitfall 3).
    """
    if status == 401:
        raise APIClientError(message="Duffel authentication failed (401)", retryable=False) from exc
    if status == 422:
        raise APIClientError(message="Duffel validation error (422)", retryable=False) from exc
    if status == 429:
        raise APIRateLimitError(message="Duffel rate limit exceeded (429)", retryable=True) from exc
    if 400 <= status < 500:
        raise APIClientError(message=f"Duffel client error ({status})", retryable=False) from exc
    if 500 <= status < 600:
        raise APIServerError(message=f"Duffel server error ({status})", retryable=True) from exc
    raise APIServerError(message=f"Duffel unknown error (status={status})", retryable=True) from exc
```

**Class skeleton** (lines 141-196 historical, simplified — drop the OAuth2 fields):
```python
class DuffelFlightClient(FlightAPIClient):
    """Concrete FlightAPIClient backed by Duffel's REST API v2.

    Static bearer-token auth (no OAuth2 token cache). search() composes
    @retry_on_failure outside call_with_breaker outside _search_impl — same
    composition as the deleted Amadeus client (D-12-class).
    """

    _OFFER_REQUESTS_PATH = "/air/offer_requests"

    def __init__(self, api_token: str, base_url: str) -> None:
        """Construct the client without performing any network I/O.

        Args:
            api_token: Duffel bearer token (raw string; caller unwraps
                Settings.duffel_api_token via .get_secret_value()).
            base_url: Always "https://api.duffel.com" (token prefix selects
                sandbox vs production).
        """
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            throw_new_error_on_trip=True,
        )
```
**Note:** Drop these instance attrs from the Amadeus analog: `_access_token`, `_expires_at`, `_token_lock`, `_REFRESH_BUFFER_SECONDS`, `_TOKEN_PATH`. Drop the `_get_token` and `_refresh_token` methods entirely.

**`search()` pattern** (D-06 offset cap — lines 354-391 historical, modified):
```python
async def search(
    self, query: FlightQuery,
    sort_by: SortBy = "price",
    max_price: Decimal | None = None,
    max_duration: int | None = None,
    max_stops: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Flight]:
    """D-06: ``offset`` is honored but capped — Duffel's single-round-trip flow
    does not support offset>0; we return offers[:limit] regardless. Avoids the
    CR-01-class double-application bug from the prior Amadeus phase.
    """
    flights = await self._fetch_with_retry_breaker(query, limit, max_stops)
    flights = _apply_filters(flights, max_price, max_duration, max_stops)
    flights = _sort_flights(flights, sort_by)
    return flights[:limit]  # D-06: cap; ignore offset
```

**`_fetch_with_retry_breaker` pattern** (lines 393-417 historical — verbatim shape, with the breaker-open mapping):
```python
@retry_on_failure(max_retries=3, backoff_base=2.0)
async def _fetch_with_retry_breaker(
    self, query: FlightQuery, limit: int, max_stops: int | None
) -> list[Flight]:
    try:
        return await call_with_breaker(
            self._breaker, self._search_impl, query, limit, max_stops
        )
    except pybreaker.CircuitBreakerError as exc:
        raise APIServerError(
            message="Duffel circuit breaker open",
            retryable=False,
        ) from exc
```

**`_search_impl` pyreqwest builder chain** (lines 419-484 historical adapted to Duffel's POST):
```python
async def _search_impl(
    self, query: FlightQuery, limit: int, max_stops: int | None
) -> list[Flight]:
    body = self._build_offer_request_body(query, max_stops)
    url = f"{self._base_url}{self._OFFER_REQUESTS_PATH}"
    try:
        async with (
            ClientBuilder().timeout(timedelta(seconds=15)).error_for_status(True).build() as client
        ):
            resp = (
                await client.post(url)
                .query({"return_offers": "true"})
                .bearer_auth(self._api_token)
                .header("Duffel-Version", _DUFFEL_VERSION)
                .header("Accept", "application/json")
                .json(body)
                .build()
                .send()
            )
            payload: dict[str, Any] = await resp.json()
    except StatusError as exc:
        status = int(exc.details.get("status", 0))
        _raise_from_http_status(status, exc)
    except RequestTimeoutError as exc:
        raise APITimeoutError(message="Duffel request timed out", retryable=True) from exc
    except ConnectError as exc:
        raise APITimeoutError(message="Duffel connection failed", retryable=True) from exc

    offers: list[dict[str, Any]] = payload["data"]["offers"]
    return [self._normalize_offer(o) for o in offers[:limit]]  # D-06 cap at impl boundary too
```

**`_build_offer_request_body` pattern** (D-07 round-trip + D-13 adult-only + D-14 max_connections — see RESEARCH Example 1):
```python
def _build_offer_request_body(
    self, query: FlightQuery, max_stops: int | None
) -> dict[str, Any]:
    """Construct the Duffel POST body. D-07 / D-13 / D-14."""
    outbound: dict[str, Any] = {
        "origin": query.origin,
        "destination": query.destination,
        "departure_date": str(query.departure_date),
    }
    if max_stops is not None:
        outbound["max_connections"] = max_stops  # D-14: server-side filter

    slices = [outbound]
    if query.return_date is not None:  # D-07: round trip
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
            "passengers": [{"type": "adult"}] * query.passengers,  # D-13
            "cabin_class": "economy",  # D-10: passes through; FlightQuery has no cabin yet
        }
    }
```

**`_normalize_offer` pattern** (D-08, D-09, D-10 — see RESEARCH Example 3):
```python
def _normalize_offer(self, offer: dict[str, Any]) -> Flight:
    """Duffel offer -> vendor-neutral Flight (D-08).

    D-09: naive datetimes get UTC attached (Pitfall 2).
    D-10: cabin lives at slices[].segments[].passengers[0].cabin_class.
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
        price=Decimal(str(offer["total_amount"])),
        currency=offer["total_currency"],
        carrier=carrier["name"],
        flight_number=f"{carrier['iata_code']}{first_seg['marketing_carrier_flight_number']}",
        duration_minutes=_iso_pt_to_minutes(slice_["duration"]),
        stops=len(segments) - 1,
        booking_class=cabin_raw.lower(),  # validator narrows
    )
```

**`health_check` / `get_flight_details` / `check_availability` stubs** (lines 333-349 + 605-637 historical) — copy verbatim shape, swap "Amadeus" → "Duffel" in messages. `health_check()` returns `True` unconditionally (no network call — RESEARCH OQ-1 recommendation).

---

### `backend/app/config.py` (config)

**Analog:** current `backend/app/config.py` (existing optional-credential field shape used for OpenAI / Anthropic).

**Settings field pattern** (lines 56-62 current — `openai_api_key` / `anthropic_api_key` shape):
```python
# OpenAI Configuration (optional)
openai_api_key: str | None = None
openai_model: str = "gpt-4o-mini"

# Anthropic Configuration (optional)
anthropic_api_key: str | None = None
anthropic_model: str = "claude-3-5-sonnet-20241022"
```

**New Duffel block to add** (D-01):
```python
# Duffel Configuration (Phase 7 — D-01).
# Optional: lifespan auto-falls-back to MockFlightAPIClient when token is None
# OR duffel_env == "mock" (D-02). SecretStr scrubs in repr/str (T-07-02).
# Pitfall 6: token MUST default to None so a fresh checkout boots without
# credentials.
duffel_api_token: SecretStr | None = None
duffel_env: Literal["test", "live", "mock"] = "test"
```
Imports to add: `from pydantic import SecretStr` (already imports `field_validator` from pydantic) and `from typing import Literal`.

---

### `backend/app/api/main.py::lifespan` (bootstrap / DI wiring)

**Analog:** current `backend/app/api/main.py` lines 49-92 (current Mock-only branch, post-Amadeus reset) **combined with** `5d7499c^:backend/app/api/main.py` Amadeus branch.

**Current Mock-only branch to replace** (lines 56-61 current):
```python
# Phase 7 (vendor switch): Amadeus integration removed; Duffel client lands
# in the next plan. Until then, the lifespan unconditionally constructs the
# mock client so the dev stack stays bootable.
flight_client: FlightAPIClient = MockFlightAPIClient(seed=42)
flight_provider = "mock"
```

**Replace with** (D-02 — see RESEARCH Pattern 1):
```python
# D-02: lifespan auto-fallback. Boot must NEVER fail because of missing
# creds (Pitfall 6). flight_provider = "real" only when DuffelFlightClient
# is constructed.
if settings.duffel_env == "mock" or settings.duffel_api_token is None:
    if settings.duffel_env != "mock":
        # Pitfall 6 / T-07-02: WARN but do not raise. The literal substring
        # "DUFFEL_API_TOKEN missing" is asserted by
        # tests/integration/test_lifespan_flight_provider.py.
        logger.warning(
            "DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient"
        )
    flight_client: FlightAPIClient = MockFlightAPIClient(seed=42)
    flight_provider = "mock"
else:
    flight_client = DuffelFlightClient(
        api_token=settings.duffel_api_token.get_secret_value(),
        base_url="https://api.duffel.com",
    )
    flight_provider = "real"
```

**Import to add at top of file:**
```python
from app.flights.duffel_client import DuffelFlightClient
```

---

### `backend/app/llm/log_scrubbing.py` (utility)

**Analog:** current `backend/app/llm/log_scrubbing.py` (the `SECRET_PATTERNS` tuple).

**Existing pattern** (lines 37-41 current):
```python
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "sk-ant-[REDACTED]"),
    (re.compile(r"sk-(?:[a-z]+-)*[A-Za-z0-9_-]{20,}"), "sk-[REDACTED]"),
    (re.compile(r'("[A-Za-z0-9_]*api_key"\s*:\s*)"[^"]+"'), r'\1"[REDACTED]"'),
)
```

**Add one tuple entry** (Pitfall 7 — order does not matter; `duffel_*` prefix never collides with `sk-*`):
```python
(re.compile(r"duffel_(test|live)_[A-Za-z0-9_-]{20,}"), "duffel_[REDACTED]"),
```

---

### `backend/app/tools/flight_search.py` (tool entry-point — D-08 cleanup)

**Analog:** current `backend/app/tools/flight_search.py`.

**Delete these symbols + their tests:**
- `normalize_amadeus_offer` (lines 141-218 current)
- `normalize_skyscanner_itinerary` (lines 221-301 current)

**Keep:** `_extract_carrier_iata`, `_to_iso_duration`, `_to_flight_search_result`, `search_flights` (the tool entry-point). The "Phase 7's real Amadeus client will populate `city` from `dictionaries.locations`" comment in `_to_flight_search_result` (lines 86-88) should be updated to reference Duffel — `Flight.origin`/`destination` already carry IATA codes from `_normalize_offer`, so the placeholder behavior is unchanged for v1.

**Update the carrier IATA path:** `_extract_carrier_iata` regex-extracts the leading 2-letter prefix from `flight_number`. `DuffelFlightClient._normalize_offer` constructs `flight_number` as `f"{carrier_iata}{number}"`, so `_extract_carrier_iata` keeps working unchanged.

**Imports to drop** when `normalize_amadeus_offer` / `normalize_skyscanner_itinerary` are deleted: `from datetime import UTC`, `from typing import Any` (verify both are unused after deletion). The `from datetime import datetime` local import inside `normalize_skyscanner_itinerary` disappears with the function.

---

### `backend/tests/unit/test_duffel_client.py` (test, unit)

**Analog:** `5d7499c^:backend/tests/unit/test_amadeus_client.py` (293 lines historical).

**Test pattern: open-breaker mapping** (lines 49-93 historical) — copy verbatim, swap `AmadeusFlightClient` → `DuffelFlightClient`, drop the `api_secret` constructor arg:
```python
@pytest.mark.asyncio
async def test_circuit_breaker_open_raises_apiservererror_not_retried() -> None:
    """Open breaker mapped to APIServerError(retryable=False) (D-13-class)."""
    client = DuffelFlightClient("dummy_token", "https://api.duffel.com")
    client._breaker = pybreaker.CircuitBreaker(
        fail_max=1, reset_timeout=60, throw_new_error_on_trip=True
    )
    impl_mock = AsyncMock(side_effect=APIServerError(message="boom", retryable=True))
    query = FlightQuery(
        origin="MAD", destination="BCN", departure_date=_future_date(), passengers=1
    )
    with (
        patch.object(client, "_search_impl", impl_mock),
        patch("tenacity.nap.time.sleep", return_value=None),
    ):
        with pytest.raises(APIServerError) as first_call:
            await client.search(query)
        assert first_call.value.retryable is False
        assert "circuit breaker open" in first_call.value.message.lower()
        with pytest.raises(APIServerError) as second_call:
            await client.search(query)
        assert second_call.value.retryable is False
    assert impl_mock.await_count == 1
```

**ClientBuilder mock chain** (lines 113-153 historical) — copy verbatim shape, but the chain methods change for Duffel POST: `.post(url).query(...).bearer_auth(...).header(...).header(...).json(...).build().send()`. The `_FakeRequestBuilder` class needs `.query`, `.bearer_auth`, `.header`, `.json`, `.build` methods returning self; `_FakeRequest.send` raises the fake `StatusError`.

**Drop these tests entirely** (no longer applicable to Duffel):
- `test_search_401_invalidates_token_cache` — no token cache.
- All `test_amadeus_token_cache.py` content (`5d7499c^:backend/tests/unit/test_amadeus_token_cache.py`) — drop wholesale.

**Add new tests** (Wave 0 from RESEARCH §Validation Architecture):
- `test_normalize_offer` — load `tests/fixtures/duffel/offer_request_response_oneway.json`, call `_normalize_offer(payload["data"]["offers"][0])`, assert TZ-aware Flight, multi-segment, all fields populated.
- `test_offset_capped` — D-06 regression-lock: `search(limit=2, offset=2)` returns `len <= 2` and the head of the offer list (CR-01-class prevention).
- `test_round_trip_two_slices` — D-07: `_build_offer_request_body(query_with_return_date, ...)` produces `len(body["data"]["slices"]) == 2`.
- `test_max_stops_mapping` — D-14: `max_stops=1` → `body["data"]["slices"][0]["max_connections"] == 1`; `max_stops=None` → key absent.
- `test_naive_datetime_normalized_to_utc` — analog of historical lines 156+; load fixture with naive `departing_at`, assert `result.departure.tzinfo == UTC`.

---

### `backend/tests/unit/test_duffel_error_mapping.py` (test, unit, parametrised)

**Analog:** `5d7499c^:backend/tests/unit/test_amadeus_error_mapping.py` (39 lines historical) — copy verbatim with two changes:
1. Import path: `from app.flights.duffel_client import _raise_from_http_status`.
2. Add the 422 row to the parametrize list.

```python
import pytest
from app.exceptions import APIClientError, APIError, APIRateLimitError, APIServerError
from app.flights.duffel_client import _raise_from_http_status

@pytest.mark.parametrize(
    ("status", "exc_type", "retryable"),
    [
        (401, APIClientError, False),
        (400, APIClientError, False),
        (404, APIClientError, False),
        (422, APIClientError, False),  # D-04: Duffel validation
        (429, APIRateLimitError, True),
        (500, APIServerError, True),
        (503, APIServerError, True),
    ],
)
def test_raise_from_http_status(
    status: int, exc_type: type[APIError], retryable: bool
) -> None:
    cause = RuntimeError("upstream")
    with pytest.raises(exc_type) as exc_info:
        _raise_from_http_status(status, cause)
    assert exc_info.value.retryable is retryable
    assert exc_info.value.__cause__ is cause
```

---

### `backend/tests/unit/test_config_duffel.py` (test, unit)

**Analog:** partial — no direct `test_config.py` survives on master. Pattern is small and bespoke: instantiate `Settings`, assert field types, exercise the env-var override.

```python
"""Locks Settings.duffel_api_token type (SecretStr | None) and
Settings.duffel_env literal narrowing (D-01).
"""
import pytest
from pydantic import SecretStr
from app.config import Settings


def test_duffel_api_token_defaults_to_none() -> None:
    """Pitfall 6: missing env var must NOT raise — token defaults to None."""
    s = Settings(duffel_api_token=None)
    assert s.duffel_api_token is None


def test_duffel_api_token_is_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    """SecretStr coercion + repr scrubbing (T-07-02)."""
    monkeypatch.setenv("DUFFEL_API_TOKEN", "duffel_test_xxxxxxxxxxxxxxxxxxxx")
    s = Settings()
    assert isinstance(s.duffel_api_token, SecretStr)
    assert "duffel_test_xxxx" not in repr(s.duffel_api_token)


def test_duffel_env_default_is_test() -> None:
    s = Settings()
    assert s.duffel_env == "test"


def test_duffel_env_rejects_invalid_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUFFEL_ENV", "staging")
    with pytest.raises(Exception):  # pydantic ValidationError
        Settings()
```

---

### `backend/tests/unit/llm/test_log_scrubbing.py` (test, unit — extend)

**Analog:** current `backend/tests/unit/llm/test_log_scrubbing.py` (Group A direct regex tests at lines 37-77).

**Existing pattern** (lines 37-50 current):
```python
def test_scrub_redacts_openai_style_key_in_freeform_string() -> None:
    assert _scrub("key=sk-abcdefghij1234567890") == "key=sk-[REDACTED]"

def test_scrub_redacts_anthropic_style_key_in_freeform_string() -> None:
    assert _scrub("key=sk-ant-api03-abcdefghij1234567890") == "key=sk-ant-[REDACTED]"
```

**Add to Group A** (Pitfall 7 — both `duffel_test_*` and `duffel_live_*`):
```python
def test_scrub_redacts_duffel_test_token() -> None:
    assert _scrub("token=duffel_test_abcdefghij1234567890") == "token=duffel_[REDACTED]"

def test_scrub_redacts_duffel_live_token() -> None:
    assert _scrub("token=duffel_live_abcdefghij1234567890") == "token=duffel_[REDACTED]"

def test_scrub_short_duffel_prefix_does_not_match() -> None:
    # < 20 chars; must not be redacted (avoids false positives)
    assert _scrub("debug duffel_test_short was here") == "debug duffel_test_short was here"
```

---

### `backend/tests/integration/test_lifespan_flight_provider.py` (test, integration — rebuild)

**Analog:** `5d7499c^:backend/tests/integration/test_lifespan_flight_provider.py` (103 lines historical).

**Pattern: lifespan branches with `with TestClient(app) as client:`** — copy verbatim with three substitutions: `amadeus_env`→`duffel_env`, `amadeus_api_key`/`amadeus_api_secret` (two fields)→`duffel_api_token` (one field), `AMADEUS_* creds missing`→`DUFFEL_API_TOKEN missing`.

```python
"""Lifespan flight-provider branch tests (Phase 7 / Plan 07-Duffel, D-01 + D-02).

The lifespan branches on ``Settings.duffel_env`` AND token presence:

* ``duffel_env == "mock"`` OR ``duffel_api_token is None`` -> MockFlightAPIClient
  + flight_provider == "mock". The missing-token branch additionally logs
  WARN ``"DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient"``.
* Otherwise -> DuffelFlightClient against ``"https://api.duffel.com"``,
  with token unpacked via SecretStr.get_secret_value().
"""
import logging
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.api.main import app
from app.flights.duffel_client import DuffelFlightClient
from app.tools.flight_client import MockFlightAPIClient


def test_lifespan_uses_mock_when_duffel_env_is_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """duffel_env == 'mock' short-circuits to MockFlightAPIClient. No WARN log."""
    monkeypatch.setattr("app.config.settings.duffel_env", "mock")
    monkeypatch.setattr("app.config.settings.duffel_api_token", None)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "mock"
        assert isinstance(app.state.flight_client, MockFlightAPIClient)


def test_lifespan_falls_back_to_mock_when_token_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """Real env + missing token -> mock fallback with WARN log."""
    monkeypatch.setattr("app.config.settings.duffel_env", "test")
    monkeypatch.setattr("app.config.settings.duffel_api_token", None)
    with (
        caplog.at_level(logging.WARNING, logger="app.api.main"),
        TestClient(app) as client,
    ):
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "mock"
        assert isinstance(app.state.flight_client, MockFlightAPIClient)
    assert any(
        "DUFFEL_API_TOKEN missing" in record.message for record in caplog.records
    )


def test_lifespan_constructs_duffel_client_with_real_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real env + present token -> DuffelFlightClient against api.duffel.com."""
    monkeypatch.setattr("app.config.settings.duffel_env", "test")
    monkeypatch.setattr(
        "app.config.settings.duffel_api_token", SecretStr("duffel_test_fake_xxxxxxxxxxxxxxxx")
    )
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.flight_provider == "real"
        assert isinstance(app.state.flight_client, DuffelFlightClient)
        assert app.state.flight_client._base_url == "https://api.duffel.com"
```

---

### `backend/tests/integration/test_health.py` (test, integration — extend)

**Analog:** current `backend/tests/integration/test_health.py` (36 lines).

**Existing pattern** (lines 14-22 current):
```python
def test_health() -> None:
    """/health returns the post-Plan-07-05 shape: status + flight_provider."""
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "flight_provider" in data
    assert data["flight_provider"] in ("real", "mock")
```

**Update the comment in `test_health_flight_provider_is_mock_without_credentials`** (lines 25-35 current) to remove the "Phase 7 vendor switch in progress" note now that the Duffel client has landed; assertion logic is unchanged (the test still expects mock when no creds are set in the test env).

---

### `backend/tests/e2e_duffel/{__init__.py, conftest.py, test_duffel_client.py}` (test, e2e gated)

**Analog:** `5d7499c^:backend/tests/e2e_amadeus/{__init__.py, conftest.py, test_amadeus_client.py}` (35 + 129 lines historical).

**conftest.py pattern** (verbatim shape, single-token simplification — drop secret arg):
```python
"""e2e_duffel pytest config — skips suite when DUFFEL_API_TOKEN env var is absent.

Deliberately does NOT inherit the httpx autouse stub from
tests/integration/conftest.py — e2e_duffel tests issue REAL HTTP traffic to
the Duffel sandbox.

Per D-11, the entire suite is skipped at collection time when
DUFFEL_API_TOKEN is unset. Skip enforced via module-level pytestmark in each
test file (conftest variables are not visible to test modules without import).
"""
import os
import pytest
from app.flights.duffel_client import DuffelFlightClient

DUFFEL_AVAILABLE = bool(os.environ.get("DUFFEL_API_TOKEN"))


@pytest.fixture(scope="module")
def duffel_client() -> DuffelFlightClient:
    """Real DuffelFlightClient against the Duffel sandbox.

    Module-scoped so the four tests share a single client instance
    (mirrors the Amadeus suite's token-cache reuse pattern though Duffel
    has no token cache).
    """
    return DuffelFlightClient(
        api_token=os.environ["DUFFEL_API_TOKEN"],
        base_url="https://api.duffel.com",
    )
```

**test_duffel_client.py — four tests per D-12** (analog: `5d7499c^:backend/tests/e2e_amadeus/test_amadeus_client.py` four-test layout):

```python
"""Real-API Duffel tests (D-12). Module-level pytestmark gates collection.

Path-isolated under backend/tests/e2e_duffel/ so default pytest and
test/test-unit/test-integration/test-e2e justfile targets do NOT collect.
Use ``just test-duffel`` (Plan adds it).

Asserts D-12 four behaviours:
  (a) auth probe — first request with valid token returns 2xx
  (b) live MAD->BCN search returns >= 1 offer (Pitfall 1; LON->NYC fallback)
  (c) full vendor-neutral Flight shape after _normalize_offer
  (d) bogus token surfaces as APIClientError(retryable=False)
"""
import os
from datetime import date, timedelta
from decimal import Decimal
import pytest
from app.exceptions import APIClientError
from app.flights.duffel_client import DuffelFlightClient
from app.flights.models import FlightQuery

DUFFEL_AVAILABLE = bool(os.environ.get("DUFFEL_API_TOKEN"))
pytestmark = pytest.mark.skipif(
    not DUFFEL_AVAILABLE, reason="DUFFEL_API_TOKEN not set"
)


@pytest.mark.asyncio
async def test_auth_probe(duffel_client: DuffelFlightClient) -> None:
    """D-12(a): valid token -> 2xx on a lightweight reference endpoint.

    RESEARCH Example 4: GET /air/airlines?limit=1 — reference data, no
    per-search quota burn. Implement as a private _auth_probe() method or
    inline a single ClientBuilder chain; do NOT use POST /air/offer_requests.
    """
    # call duffel_client._auth_probe() or equivalent
    assert await duffel_client._auth_probe() is True


@pytest.mark.asyncio
async def test_real_search_returns_results(duffel_client: DuffelFlightClient) -> None:
    """D-12(b): MAD->BCN 30 days out returns >= 1 offer (Pitfall 1)."""
    query = FlightQuery(
        origin="MAD", destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )
    results = await duffel_client.search(query, limit=5)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_vendor_neutral_shape(duffel_client: DuffelFlightClient) -> None:
    """D-12(c): first result satisfies the vendor-neutral Flight contract."""
    query = FlightQuery(
        origin="MAD", destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )
    results = await duffel_client.search(query, limit=5)
    first = results[0]
    assert first.id
    assert first.origin == "MAD"
    assert first.price > Decimal("0")
    assert isinstance(first.currency, str) and len(first.currency) == 3
    assert first.carrier
    assert first.duration_minutes > 0
    assert first.departure.tzinfo is not None  # D-09: TZ attached


@pytest.mark.asyncio
async def test_error_mapping_401_with_bogus_token() -> None:
    """D-12(d): bogus token -> APIClientError(retryable=False)."""
    bad_client = DuffelFlightClient(
        api_token="duffel_test_invalid_xxxxxxxxxxxxxxxx",
        base_url="https://api.duffel.com",
    )
    query = FlightQuery(
        origin="MAD", destination="BCN",
        departure_date=date.today() + timedelta(days=30),
        passengers=1,
    )
    with pytest.raises(APIClientError) as exc_info:
        await bad_client.search(query)
    assert exc_info.value.retryable is False
```

---

### `backend/tests/fixtures/duffel/offer_request_response_{oneway,roundtrip}.json` (fixtures — capture from sandbox)

**Analog:** partial — fixtures are vendor-shape-specific. Capture once during Wave 0 with `DUFFEL_API_TOKEN` set; commit JSON files; offline tests then drive `_normalize_offer` forever. Shape reference is the Duffel SDK source cited in RESEARCH §Sources (`OfferSliceSegmentPassenger`, `OfferSlice`, `Offer.total_amount`, etc.).

Required fields per fixture (see RESEARCH Example 3):
- `data.offers[].id`, `total_amount`, `total_currency`
- `data.offers[].slices[].duration` (e.g. `"PT1H30M"`)
- `data.offers[].slices[].segments[].departing_at` / `arriving_at` (naive ISO 8601 — Pitfall 2)
- `data.offers[].slices[].segments[].origin.iata_code` / `destination.iata_code`
- `data.offers[].slices[].segments[].marketing_carrier.name` / `iata_code`
- `data.offers[].slices[].segments[].marketing_carrier_flight_number`
- `data.offers[].slices[].segments[].passengers[0].cabin_class`

`offer_request_response_roundtrip.json` differs only by having two slices in each offer (return leg).

---

### `justfile` (config)

**Analog:** existing `test`/`test-unit`/`test-integration` targets (lines 16-30 current).

**Existing pattern:**
```makefile
# Run unit tests only
test-unit:
    cd backend && uv run pytest tests/unit/

# Run integration tests only
test-integration:
    cd backend && uv run pytest tests/integration/
```

**Add a new target after `test-e2e`:**
```makefile
# Run real-API Duffel tests (gated on DUFFEL_API_TOKEN env var)
test-duffel:
    cd backend && uv run pytest tests/e2e_duffel/ -v
```

---

### `.github/workflows/ci.yml` (config)

**Analog:** existing `e2e:` job (lines 89-119 current).

**Existing job pattern:**
```yaml
e2e:
  name: E2E
  runs-on: ubuntu-latest
  steps:
    - name: Checkout
      uses: actions/checkout@v4
    - name: Set up Python 3.13
      uses: actions/setup-python@v5
      with:
        python-version: "3.13"
    - name: Install uv
      uses: astral-sh/setup-uv@v4
    - name: Cache uv virtualenv
      uses: actions/cache@v4
      with:
        path: backend/.venv
        key: uv-${{ runner.os }}-${{ hashFiles('backend/uv.lock') }}
    - name: Install dependencies
      working-directory: backend
      run: uv sync --frozen
    - name: Run E2E tests
      working-directory: backend
      run: uv run pytest tests/e2e/
```

**Add a new job `duffel-e2e`** (D-11 — gated on `secrets.DUFFEL_API_TOKEN` AND `vars.DUFFEL_E2E_ENABLED == 'true'`):
```yaml
duffel-e2e:
  name: Duffel E2E
  runs-on: ubuntu-latest
  if: vars.DUFFEL_E2E_ENABLED == 'true'
  steps:
    - name: Checkout
      uses: actions/checkout@v4
    - name: Set up Python 3.13
      uses: actions/setup-python@v5
      with:
        python-version: "3.13"
    - name: Install uv
      uses: astral-sh/setup-uv@v4
    - name: Cache uv virtualenv
      uses: actions/cache@v4
      with:
        path: backend/.venv
        key: uv-${{ runner.os }}-${{ hashFiles('backend/uv.lock') }}
    - name: Install dependencies
      working-directory: backend
      run: uv sync --frozen
    - name: Run Duffel E2E tests
      working-directory: backend
      env:
        DUFFEL_API_TOKEN: ${{ secrets.DUFFEL_API_TOKEN }}
      run: uv run pytest tests/e2e_duffel/ -v
```

PR CI never requires the secret because the job is fully skipped when `vars.DUFFEL_E2E_ENABLED` is unset/false.

---

## Shared Patterns

### Pattern S1: Async-safe retry + breaker + HTTP composition

**Source:** `backend/app/tools/retry.py` + `backend/app/tools/circuit_breaker.py` (current).

**Apply to:** `DuffelFlightClient._fetch_with_retry_breaker` and any future vendor client.

**Order is fixed by D-12-class semantics:** `@retry_on_failure` outer, `call_with_breaker` inner, pyreqwest call innermost. Open-breaker mapped to `APIServerError(retryable=False)` so the tenacity predicate `_is_retryable` (lines 68-71 of `retry.py`) skips retries into an open circuit.

```python
@retry_on_failure(max_retries=3, backoff_base=2.0)
async def _fetch_with_retry_breaker(self, *args) -> ...:
    try:
        return await call_with_breaker(self._breaker, self._search_impl, *args)
    except pybreaker.CircuitBreakerError as exc:
        raise APIServerError(message="<vendor> circuit breaker open", retryable=False) from exc
```

### Pattern S2: pyreqwest builder chain (POST + bearer + headers + JSON)

**Source:** verified pyreqwest chain shape (RESEARCH Pattern 2; deleted Amadeus client used the GET form).

**Apply to:** `DuffelFlightClient._search_impl` and any future POST-bearing vendor.

```python
async with (
    ClientBuilder().timeout(timedelta(seconds=15)).error_for_status(True).build() as client
):
    resp = (
        await client.post(url)
        .query({...})
        .bearer_auth(token)
        .header("Duffel-Version", _DUFFEL_VERSION)
        .header("Accept", "application/json")
        .json(body)
        .build()
        .send()
    )
    payload = await resp.json()
```
**Critical:** `error_for_status(True)` so non-2xx responses raise `StatusError` instead of returning a body the JSON parser will choke on (CR-02-class regression).

### Pattern S3: HTTP-status-driven error mapping

**Source:** `5d7499c^:backend/app/flights/amadeus_client.py:103-138` historical (D-04 carry-over).

**Apply to:** Every vendor client. Single module-level `_raise_from_http_status(status, exc) -> NoReturn` helper. Body content NEVER appears in exception messages (Pitfall 3 / T-07-02).

### Pattern S4: SecretStr + lifespan auto-fallback for optional credentials

**Source:** current `backend/app/config.py` (existing `openai_api_key: str | None = None` shape) + `5d7499c^:backend/app/api/main.py` lifespan branch.

**Apply to:** Any future vendor that requires a credential but should not block boot when the credential is absent (Pitfall 6).

Pattern:
1. Settings field defaults to `None` (`SecretStr | None = None`).
2. Lifespan checks `settings.<token> is None` AND/OR a `_env: Literal[...]` field to decide between mock and real client.
3. Missing-creds branch logs ONE WARN (asserted by tests) and constructs the mock.
4. `app.state.<provider>_provider = "real" | "mock"` so `/health` can surface the active mode.

### Pattern S5: Path-isolated gated e2e suite

**Source:** `5d7499c^:backend/tests/e2e_amadeus/` historical (D-11 carry-over).

**Apply to:** Any future real-API vendor test suite.

1. New directory `backend/tests/e2e_<vendor>/` — NOT under `backend/tests/e2e/` (which has its own collection rules).
2. Module-level `pytestmark = pytest.mark.skipif(not <VENDOR>_AVAILABLE, reason=...)` in each test file (conftest variables are not visible to test modules without import).
3. New justfile target `test-<vendor>` for path-explicit collection.
4. New CI job in `.github/workflows/ci.yml` gated on `if: vars.<VENDOR>_E2E_ENABLED == 'true'` AND `env: <SECRET>: ${{ secrets.<SECRET> }}`.
5. Conftest deliberately does NOT inherit any integration-conftest stubs — these tests issue real HTTP.

### Pattern S6: ABC-implementation pair behind FastAPI lifespan

**Source:** current `backend/app/tools/flight_client.py` (`FlightAPIClient` ABC + `MockFlightAPIClient`) + Phase 6 `MessageStore`/`PostgresMessageStore` precedent (cited in CONTEXT §Established Patterns).

**Apply to:** All vendor clients. The route layer / LangChain tool consumes the ABC via `app.state.flight_client` (DI seam from Phase 5/6). New impls slot in at the lifespan branch only — zero route-layer churn.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/tests/fixtures/duffel/offer_request_response_*.json` | test fixture | n/a | Fixtures are vendor-shape-specific; must be captured once from the Duffel sandbox (Wave 0 task). RESEARCH Example 3 + RESEARCH §Sources cite the Duffel SDK model definitions for shape reference. |
| `backend/tests/unit/test_config_duffel.py` | test (unit, Settings) | n/a | The historical `test_config.py` was deleted with the Amadeus removal commit. Pattern is small (instantiate `Settings`, assert field types) — no strong analog needed; sketch supplied above. |

## Metadata

**Analog search scope:**
- Current `master`: `backend/app/`, `backend/tests/`, `backend/justfile` (root), `.github/workflows/`
- Historical: `git show 5d7499c^:` for all files deleted in commit `5d7499c` (Amadeus removal)

**Files scanned:** ~30 (12 read in full; remainder via Grep / git show)

**Pattern extraction date:** 2026-06-06

**Key insight for the planner:** Phase 7 is plumbing assembly atop a deleted-but-recoverable analog. The Duffel client is materially smaller than the Amadeus one (~250 vs ~340 LOC) because the entire OAuth2 token-cache layer (`_get_token`, `_refresh_token`, `asyncio.Lock`, double-checked locking, malformed-body guard, proactive expiry buffer) does not apply. Inheritance from the Amadeus analog should be `git show 5d7499c^:<path>`-mediated copy + simplification — not greenfield design.
