# Phase 7: Real Flight API - Research

**Researched:** 2026-06-05
**Domain:** Amadeus REST API / pyreqwest async HTTP / tenacity retry / pybreaker circuit breaker
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Token cache: in-process with proactive refresh, inline-on-call + concurrent-refresh lock. Cache token + `expires_at`. On each call, if `now >= expires_at - 60s`, acquire `asyncio.Lock` and refresh; concurrent callers wait on the same lock.
- **D-02:** No persistence across restarts. First call after boot fetches a fresh token. OAuth2 client_credentials against `https://test.api.amadeus.com/v1/security/oauth2/token` (or prod equivalent).
- **D-03:** Token refresh failures bubble as `APIError(retryable=True)`.
- **D-04:** `Settings.amadeus_env: Literal["test", "prod", "mock"] = "test"`. Base URL: `test` → `https://test.api.amadeus.com`, `prod` → `https://api.amadeus.com`, `mock` → no client.
- **D-05:** Auto-fallback at lifespan: if `amadeus_env != "mock"` and either cred missing, log WARN `"AMADEUS_* creds missing — falling back to MockFlightAPIClient"` and instantiate `MockFlightAPIClient`. No startup failure.
- **D-06:** Healthcheck endpoint reports `flight_provider: "real" | "mock"`.
- **D-07:** Full Phase 4.6 vendor-neutral contract including multi-segment journeys and layovers.
- **D-08:** Best-effort fields (terminal, fare class, baggage). Missing values omitted, not stubbed.
- **D-09:** No raw-payload escape hatch. Vendor-neutral shape is the only output.
- **D-10:** Replace `backend/app/tools/retry.py` project-wide with tenacity-based implementation. Preserve existing public API (`max_retries`, `backoff_base`, `exceptions` params). Add `tenacity` to `pyproject.toml`.
- **D-11:** Defaults: `max_retries=3`, exponential backoff (`backoff_base=2.0`), retry on `APIError(retryable=True)`. No jitter, no `Retry-After` parsing. 429 + 5xx → `retryable=True`; 4xx (non-429) → `retryable=False`.
- **D-12:** Circuit breaker via `pybreaker` around `AmadeusFlightClient.search` (and other live-call methods). Compose: tenacity wraps inner HTTP call, pybreaker wraps the full retry block. `pybreaker` to `pyproject.toml`. Defaults: open after 5 consecutive failures, 60s reset timeout.
- **D-13:** Open-breaker raises `APIError` mapped from `pybreaker.CircuitBreakerError`. Caller propagates; chat layer surfaces per Phase 4.7 `StreamEvent` error path.
- **D-14:** Real-API tests in `backend/tests/e2e_amadeus/`. Default `pytest`, `just test`, `just test-unit`, `just test-integration`, `just test-e2e` do NOT run them. Dedicated CI job gated on `AMADEUS_*` secrets. PR CI never requires keys.
- **D-15:** Tests assert: token fetch + cache, real search returns ≥1 result for a known route, error mapping, full vendor-neutral shape after mapping.

### Claude's Discretion

- Exact tenacity API surface (`@retry` decorator vs `Retrying` class) — pick whichever maps more cleanly onto the current `retry_on_failure` signature; preserve callers.
- Module layout: `backend/app/flights/amadeus_client.py` (or similar) — pattern-match Phase 6's MessageStore/PostgresMessageStore split.
- Whether circuit-breaker thresholds are Settings-driven or hardcoded — lean toward hardcoded for v1, Settings if trivial.
- Healthcheck endpoint placement — extend existing `/health` if present, otherwise add minimal endpoint.

### Deferred Ideas (OUT OF SCOPE)

- Cross-vendor flight clients (Skyscanner, Google)
- In-process result caching with TTL
- Aggressive retry tuning (jitter, Retry-After header parsing)
- Settings-driven circuit breaker thresholds
- Rate limiting (ADR-009)
- Raw vendor payload exposure
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-real-flight-api | Replace MockFlightAPIClient with real Amadeus client behind FlightAPIClient ABC; pyreqwest for outbound HTTP; retry + circuit breaker; mock as test default; gated integration tests; credential docs. | All sections below cover the full implementation surface: Amadeus auth, endpoint mapping, pyreqwest patterns, tenacity wrapper, pybreaker async pattern, lifespan wiring, test gating. |
</phase_requirements>

---

## Summary

Phase 7 slots a real Amadeus HTTP client behind the existing `FlightAPIClient` ABC. The codebase already has most of the pieces: the ABC itself, the vendor-neutral `FlightResult`/`FlightSegment` models, the `normalize_amadeus_offer()` function in `flight_search.py`, and the `APIError` hierarchy with `retryable` flag. The implementation work is integrating pyreqwest for outbound HTTP, an asyncio.Lock token cache for OAuth2, replacing the hand-rolled `retry.py` with a tenacity wrapper that preserves the existing public API, and wiring in pybreaker as an async-safe circuit breaker around live Amadeus calls.

The most important discovery from live verification: pybreaker's `@decorator` syntax does NOT correctly trip the circuit on async functions (it wraps the coroutine object return, not the awaited result). The correct pattern is a manual `with_breaker()` helper that calls `state.before_call()` / `state._handle_error()` / `state._handle_success()` around `await`. This pattern was verified to work correctly (see Code Examples §Circuit Breaker Async-Safe Pattern).

The tenacity `@retry` decorator was verified to work correctly on async functions in Python 3.13. The correct replacement for the hand-rolled `retry_on_failure` is a thin wrapper using `retry(stop=stop_after_attempt(max_retries+1), wait=wait_exponential(multiplier=backoff_base), retry=retry_if_exception(...), reraise=True)`. The `reraise=True` flag is critical — without it tenacity raises `RetryError` instead of the original exception.

**Primary recommendation:** Implement `AmadeusFlightClient` in `backend/app/flights/amadeus_client.py` following the Phase 6 `PostgresMessageStore` split pattern. Replace `retry.py` with a tenacity wrapper in `backend/app/tools/retry.py` (same path, same public API). Wire the async-safe pybreaker pattern inside the client's HTTP methods.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Amadeus OAuth2 token lifecycle | API / Backend (`AmadeusFlightClient`) | — | Outbound auth is a backend concern; token must not leak to frontend |
| Flight search HTTP call | API / Backend (`AmadeusFlightClient`) | — | External API calls always backend; pyreqwest is backend-only per ADR-008 |
| Vendor-neutral field mapping | API / Backend (`normalize_amadeus_offer`) | — | Already implemented in Phase 4.6; Amadeus client calls this function |
| Retry + circuit breaker | API / Backend (decorator layer) | — | Cross-cutting infra wrapping the HTTP tier; transparent to routes |
| Auto-fallback to mock | API / Backend (`lifespan`) | — | Startup-time decision; routes and tools are unaware of which impl is active |
| Flight provider visibility | API / Backend (`/health` endpoint) | — | Observability endpoint; no frontend change required |
| Real-API test gating | CI / GitHub Actions | — | Secret-gated job; path-isolated from default test suite |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyreqwest` | `>=0.12.0` | Outbound HTTP to Amadeus (token + search) | Mandated by ADR-008; Rust-based async HTTP; already in project conventions |
| `tenacity` | `>=9.1.2` | Retry with exponential backoff | Battle-tested retry library; replaces hand-rolled `retry.py`; already in venv (pulled by google-genai) |
| `pybreaker` | `>=1.4.1` | Circuit breaker pattern | Lightweight pure-Python CB; `@decorator` and manual state API verified |

[VERIFIED: npm registry] — tenacity 9.1.4 published 2026-02-07 at pypi.org/project/tenacity
[VERIFIED: npm registry] — pybreaker 1.4.1 published 2025-09-21 at pypi.org/project/pybreaker
[VERIFIED: npm registry] — pyreqwest 0.12.0 published 2026-05-09 at pypi.org/project/pyreqwest (github.com/MarkusSintonen/pyreqwest)

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `asyncio.Lock` | stdlib | Concurrent token-refresh guard | Built-in; no dep needed |
| `pydantic.SecretStr` | (pydantic already in project) | Type for API key fields in Settings | Prevents accidental secret logging |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyreqwest | httpx | httpx is already in dev-deps but ADR-008 mandates pyreqwest for production outbound HTTP |
| pybreaker | hand-rolled CB | pybreaker's state machine handles open/half-open/closed correctly; hand-rolling reintroduces the exact complexity it prevents |
| tenacity @retry | Retrying class | @retry is simpler for wrapping existing decorator API; Retrying class is better for inline blocks — @retry chosen to preserve existing call-site signature |

**Installation:**
```bash
uv add pyreqwest pybreaker tenacity
```

Note: `tenacity` may already be in the lockfile as an indirect dependency of `google-genai`; the explicit dep pin ensures version floor.

**Version verification (performed during research):**
- `tenacity 9.1.4` — verified via PyPI JSON API (already installed at 9.1.2 in .venv)
- `pybreaker 1.4.1` — verified via PyPI JSON API
- `pyreqwest 0.12.0` — verified via PyPI JSON API; source repo confirmed at github.com/MarkusSintonen/pyreqwest

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| tenacity | PyPI | ~10 yrs | Very high (indirect dep of many major libs) | github.com/jd/tenacity | [OK] | Approved |
| pybreaker | PyPI | ~10 yrs | Moderate | pypi.org/project/pybreaker/ | [OK] | Approved |
| pyreqwest | PyPI | ~1 yr (0.12.0: 2026-05-09) | Moderate | github.com/MarkusSintonen/pyreqwest | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

slopcheck ran successfully on all three packages: `3 OK`.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser
   │
   ▼
FastAPI /api/chat (SSE)
   │
   ▼
ChatService.chat_stream()
   │
   └─► search_flights(ctx: RunContext[ChatDeps])
              │
              ▼
       ctx.deps.flight_client  ←── lifespan sets this
              │
    ┌─────────┴──────────┐
    │                    │
AmadeusFlightClient   MockFlightAPIClient
    │                  (test default /
    │                   fallback when
    │                   creds absent)
    │
    ├── TokenCache (asyncio.Lock, expires_at)
    │       │
    │       └─► POST /v1/security/oauth2/token (pyreqwest)
    │
    └── pybreaker(CircuitBreaker)
              │
              └─► tenacity @retry_on_failure
                       │
                       └─► pyreqwest GET /v2/shopping/flight-offers
                                  │
                               Amadeus API
                                  │
                           normalize_amadeus_offer()
                                  │
                          FlightResult (vendor-neutral)
```

### Recommended Project Structure

```
backend/app/
├── flights/
│   ├── __init__.py
│   ├── models.py          # Already exists — FlightResult, FlightSegment, etc.
│   └── amadeus_client.py  # NEW — AmadeusFlightClient(FlightAPIClient)
├── tools/
│   ├── flight_client.py   # Already exists — FlightAPIClient ABC + MockFlightAPIClient
│   ├── flight_search.py   # Already exists — normalize_amadeus_offer() already here
│   └── retry.py           # REPLACE internals — preserve public retry_on_failure() API
backend/tests/
├── unit/
│   └── test_retry.py      # Update for tenacity — existing tests should pass unchanged
├── integration/
│   └── (unchanged — mock client remains default)
└── e2e_amadeus/           # NEW — real-API tests gated on AMADEUS_* secrets
    ├── __init__.py
    ├── conftest.py         # pytest skipif(no AMADEUS_API_KEY) fixture
    └── test_amadeus_client.py
```

### Pattern 1: OAuth2 Token Cache with Concurrent-Refresh Lock

**What:** Cache bearer token + expiry on the client instance. Proactively refresh 60s before expiry. One refresh per expiry window via `asyncio.Lock`.

**When to use:** Any long-lived client that authenticates per-request with a bearer token.

```python
# Source: D-01/D-02 from 07-CONTEXT.md + verified asyncio.Lock pattern
import asyncio
from datetime import UTC, datetime, timedelta
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import StatusError, RequestTimeoutError
from app.exceptions import APIError

class AmadeusFlightClient(FlightAPIClient):
    _REFRESH_BUFFER_SECONDS = 60  # refresh 60s before actual expiry

    def __init__(self, api_key: str, api_secret: str, base_url: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url
        self._access_token: str | None = None
        self._expires_at: datetime = datetime.min.replace(tzinfo=UTC)
        self._token_lock = asyncio.Lock()

    async def _get_token(self) -> str:
        """Return cached token, refreshing proactively if near-expiry."""
        now = datetime.now(UTC)
        if self._access_token and now < self._expires_at - timedelta(seconds=self._REFRESH_BUFFER_SECONDS):
            return self._access_token  # fast path: token still fresh

        async with self._token_lock:
            # Double-checked locking: re-check after acquiring lock
            now = datetime.now(UTC)
            if self._access_token and now < self._expires_at - timedelta(seconds=self._REFRESH_BUFFER_SECONDS):
                return self._access_token

            return await self._refresh_token()

    async def _refresh_token(self) -> str:
        """Fetch a new token from Amadeus. Raises APIError(retryable=True) on failure."""
        token_url = f"{self._base_url}/v1/security/oauth2/token"
        try:
            async with ClientBuilder().timeout(timedelta(seconds=10)).build() as client:
                resp = await (
                    client.post(token_url)
                    .form({
                        "grant_type": "client_credentials",
                        "client_id": self._api_key,
                        "client_secret": self._api_secret,
                    })
                    .build()
                    .send()
                )
                body = await resp.json()
                self._access_token = body["access_token"]
                self._expires_at = datetime.now(UTC) + timedelta(seconds=body["expires_in"])
                return self._access_token
        except Exception as exc:
            # Any refresh failure is retryable — caller's tenacity layer handles it
            raise APIError(message=f"Amadeus token refresh failed: {exc}", retryable=True) from exc
```

[CITED: developers.amadeus.com/self-service/apis-docs/guides/authorization — token endpoint + response shape]

### Pattern 2: Tenacity Wrapper Preserving Existing Public API

**What:** Drop-in replacement for hand-rolled `retry.py`. Same decorator signature, tenacity internals.

**When to use:** Replacing `backend/app/tools/retry.py` — all existing call sites keep working.

```python
# Source: verified with tenacity 9.1.2 in .venv during research
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from typing import ParamSpec, TypeVar, Callable, Awaitable
from app.exceptions import APIError

P = ParamSpec("P")
R = TypeVar("R")


def retry_on_failure(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (APIError,),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Tenacity-backed retry with exponential backoff for async functions.

    Preserves the public API of the hand-rolled version in app/tools/retry.py.
    CRITICAL: reraise=True ensures the original exception propagates (not RetryError).

    Args:
        max_retries: Maximum number of retry attempts (default: 3).
        backoff_base: Multiplier for wait_exponential (default: 2.0).
        exceptions: Exception types to catch and potentially retry.

    Returns:
        Decorator that wraps async functions with retry logic.
    """
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(max_retries + 1),   # +1: initial attempt counts
        wait=wait_exponential(multiplier=backoff_base),
        retry=retry_if_exception(
            lambda e: isinstance(e, exceptions) and getattr(e, "retryable", False)
        ),
        reraise=True,  # MUST be True — otherwise tenacity raises RetryError, not APIError
    )
```

[VERIFIED: npm registry] — tenacity 9.1.4; pattern tested live against 9.1.2 in project venv.

**Key verification result:** `@retry` correctly preserves `__name__` / `__doc__` via `@wraps`. `iscoroutinefunction(decorated)` returns `True` for async functions. Non-retryable `APIClientError` (retryable=False) raises on the first attempt (call_count=1, verified).

### Pattern 3: Circuit Breaker Async-Safe Wrapper

**What:** pybreaker's `@decorator` does NOT correctly trip on async functions — the decorator wraps the coroutine object (returned synchronously by the async function) rather than awaiting it, so exceptions never propagate back to pybreaker's counter. The correct pattern uses pybreaker's state machine methods directly.

**Critical finding:** Verified via live test: `@cb` decorator on an async function that raises an exception does NOT increment the fail counter — the circuit never opens. `state.before_call()` + `state._handle_error()` + `state._handle_success()` pattern correctly trips after `fail_max` failures.

```python
# Source: verified in research session with pybreaker 1.4.1
import pybreaker
from app.exceptions import APIError, APIRateLimitError, APIServerError, APITimeoutError
from typing import TypeVar, Callable, Awaitable, Any, Coroutine

T = TypeVar("T")


async def _call_with_breaker(
    breaker: pybreaker.CircuitBreaker,
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Async-safe circuit breaker wrapper.

    pybreaker's @decorator does not handle async functions correctly —
    it wraps the coroutine object, not the awaited result, so exceptions
    never reach the circuit breaker's failure counter. This manual wrapper
    calls state.before_call() (raises CircuitBreakerError if circuit is open)
    and then updates the state after the awaited result.

    This pattern was verified against pybreaker 1.4.1 in research.
    """
    breaker.state.before_call(coro_fn, *args, **kwargs)
    try:
        result = await coro_fn(*args, **kwargs)
    except BaseException as exc:
        if breaker.is_system_error(exc):
            breaker.state._handle_error(exc, reraise=False)  # noqa: SLF001
        raise
    else:
        breaker.state._handle_success()
        return result


# Usage on AmadeusFlightClient:
class AmadeusFlightClient(FlightAPIClient):
    def __init__(self, ...) -> None:
        ...
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            throw_new_error_on_trip=True,
        )

    @retry_on_failure(max_retries=3, backoff_base=2.0)
    async def search(self, query: FlightQuery, ...) -> list[Flight]:
        try:
            return await _call_with_breaker(self._breaker, self._search_impl, query, ...)
        except pybreaker.CircuitBreakerError as exc:
            raise APIServerError(message=f"Circuit breaker open: {exc}", retryable=False) from exc
```

[CITED: github.com/danielfm/pybreaker — state machine API, CircuitBreakerError]

**Composition order:** `@retry_on_failure` wraps `_call_with_breaker(...)` which wraps `_search_impl`. So: retry → breaker → HTTP call. Each retry attempt checks the circuit; if the circuit opens mid-retry sequence, tenacity's reraise=True propagates the `APIServerError` immediately.

### Pattern 4: pyreqwest Async Client Usage

**What:** pyreqwest uses a builder pattern. The client is a context manager; each request is also built via chained calls.

```python
# Source: github.com/MarkusSintonen/pyreqwest tests (verified in research)
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import StatusError, RequestTimeoutError, ConnectError
from datetime import timedelta

async def _search_impl(self, query: FlightQuery, ...) -> list[Flight]:
    token = await self._get_token()
    params = {
        "originLocationCode": query.origin,
        "destinationLocationCode": query.destination,
        "departureDate": str(query.departure_date),
        "adults": str(query.passengers),
        "max": str(limit),
        "currencyCode": "USD",
    }
    try:
        async with ClientBuilder().timeout(timedelta(seconds=30)).error_for_status(True).build() as client:
            resp = await (
                client.get(f"{self._base_url}/v2/shopping/flight-offers")
                .bearer_auth(token)      # sets Authorization: Bearer <token>
                .query(params)           # URL query parameters
                .build()
                .send()
            )
            body = await resp.json()
    except StatusError as exc:
        status = exc.details.get("status", 0)
        _raise_from_http_status(status, exc)
    except RequestTimeoutError as exc:
        raise APITimeoutError(message=f"Amadeus request timed out: {exc}") from exc
    except ConnectError as exc:
        raise APITimeoutError(message=f"Amadeus connection failed: {exc}", retryable=True) from exc

    return _parse_flight_offers(body)
```

**pyreqwest exception hierarchy (verified):**
- `StatusError` — HTTP 4xx/5xx; access status via `e.details["status"]`
- `RequestTimeoutError` — read/connect timeout; MRO includes `TimeoutError`
- `ConnectError` — connection refused/failed; subclass of `NetworkError`
- `ConnectTimeoutError` — subclass of `RequestTimeoutError`
- `ReadTimeoutError` — subclass of `RequestTimeoutError`

### Pattern 5: Amadeus → APIError Error Mapping

```python
# Source: Amadeus docs (HTTP status semantics) + D-11 from CONTEXT.md
from app.exceptions import (
    APIClientError, APIRateLimitError, APIServerError, APITimeoutError
)

def _raise_from_http_status(status: int, exc: Exception) -> None:
    """Map Amadeus HTTP status to our APIError hierarchy."""
    if status == 401:
        # Token bad/expired — force cache invalidation before raising
        raise APIClientError(
            message=f"Amadeus authentication failed (401) — token invalidated",
            retryable=False,
        ) from exc
    elif status == 429:
        raise APIRateLimitError(
            message="Amadeus rate limit exceeded (429)",
            retryable=True,
        ) from exc
    elif status >= 500:
        raise APIServerError(
            message=f"Amadeus server error ({status})",
            retryable=True,
        ) from exc
    else:  # other 4xx (400, 404, etc.)
        raise APIClientError(
            message=f"Amadeus client error ({status})",
            retryable=False,
        ) from exc
```

### Pattern 6: Lifespan Auto-Fallback

```python
# Source: D-04/D-05 from CONTEXT.md + existing lifespan pattern in main.py
from app.config import settings
from app.tools.flight_client import MockFlightAPIClient
from app.flights.amadeus_client import AmadeusFlightClient

# Inside lifespan():
if (
    settings.amadeus_env == "mock"
    or settings.amadeus_api_key is None
    or settings.amadeus_api_secret is None
):
    if settings.amadeus_env != "mock":
        logger.warning(
            "AMADEUS_* creds missing — falling back to MockFlightAPIClient"
        )
    flight_client: FlightAPIClient = MockFlightAPIClient(seed=42)
    flight_provider = "mock"
else:
    base_url = (
        "https://test.api.amadeus.com"
        if settings.amadeus_env == "test"
        else "https://api.amadeus.com"
    )
    flight_client = AmadeusFlightClient(
        api_key=settings.amadeus_api_key.get_secret_value(),
        api_secret=settings.amadeus_api_secret.get_secret_value(),
        base_url=base_url,
    )
    flight_provider = "real"

app.state.flight_provider = flight_provider  # consumed by /health
```

### Pattern 7: Settings Additions

```python
# Source: D-04 from CONTEXT.md + CLAUDE.md "Tunable thresholds live on Settings"
from typing import Literal
from pydantic import SecretStr

class Settings(BaseSettings):
    # ... existing fields ...

    # Amadeus Flight API (Phase 7)
    amadeus_env: Literal["test", "prod", "mock"] = "test"
    amadeus_api_key: SecretStr | None = None
    amadeus_api_secret: SecretStr | None = None
    # Circuit breaker tunables (hardcoded v1 defaults; Settings for future override)
    amadeus_breaker_fail_max: int = 5
    amadeus_breaker_reset_timeout: int = 60
```

Note: `SecretStr` ensures `str(settings.amadeus_api_key)` returns `'**********'` rather than the actual key, preventing accidental log leaks. Access raw value with `.get_secret_value()`.

### Pattern 8: Health Endpoint Extension

The existing `/health` endpoint is at `GET /health` in `routes.py`. Extend it to surface `flight_provider`:

```python
# Source: existing routes.py + D-06 from CONTEXT.md
@router.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    """Health check endpoint."""
    flight_provider = getattr(request.app.state, "flight_provider", "mock")
    return {"status": "healthy", "flight_provider": flight_provider}
```

### Pattern 9: Amadeus Field Mapping (already implemented in Phase 4.6)

The `normalize_amadeus_offer()` function in `flight_search.py` already implements the mapping. The Amadeus response fixture used in tests (from `test_tool_json_normalization.py`) confirms the exact field paths:

```
Amadeus response → vendor-neutral target:
data[].id                                           → FlightResult.id
data[].itineraries[0].duration                      → FlightResult.total_duration (ISO 8601)
data[].itineraries[0].segments[].id                 → FlightSegment.id
data[].itineraries[0].segments[].departure.iataCode → FlightEndpoint.iata_code
data[].itineraries[0].segments[].departure.at       → FlightEndpoint.at (local datetime, NO TZ)
data[].itineraries[0].segments[].departure.terminal → FlightEndpoint.terminal (optional)
data[].itineraries[0].segments[].arrival.iataCode   → FlightEndpoint.iata_code
data[].itineraries[0].segments[].arrival.at         → FlightEndpoint.at
data[].itineraries[0].segments[].carrierCode        → CarrierInfo.iata_code
data[].itineraries[0].segments[].number             → FlightSegment.flight_number
data[].itineraries[0].segments[].duration           → FlightSegment.duration (ISO 8601)
data[].itineraries[0].segments[].numberOfStops      → FlightSegment.number_of_stops
data[].price.total                                  → PriceInfo.amount (Decimal)
data[].price.currency                               → PriceInfo.currency
data[].travelerPricings[0].fareDetailsBySegment[0].cabin → FlightResult.booking_class
dictionaries.carriers[carrierCode]                  → CarrierInfo.name
dictionaries.locations[iataCode].cityCode           → FlightEndpoint.city
```

**Critical: Amadeus `departure.at` is a LOCAL datetime string with NO timezone offset** (e.g., `"2024-11-01T08:00:00"`). `datetime.fromisoformat()` returns a naive datetime. The `FlightEndpoint.at` field requires a timezone-aware datetime. Phase 7 must either attach UTC (safe for sandbox) or perform airport-code timezone lookup. Phase 4.6 tests use TZ-aware strings in the fixture — the production client must add timezone info before constructing the model.

### Pattern 10: e2e_amadeus Test Structure

```python
# Source: CLAUDE.md test conventions + D-14/D-15 from CONTEXT.md
import os
import pytest

AMADEUS_AVAILABLE = (
    os.environ.get("AMADEUS_API_KEY") is not None
    and os.environ.get("AMADEUS_API_SECRET") is not None
)

pytestmark = pytest.mark.skipif(
    not AMADEUS_AVAILABLE,
    reason="AMADEUS_API_KEY and AMADEUS_API_SECRET not set",
)

@pytest.mark.asyncio
async def test_token_fetch_and_cache() -> None:
    """Real token fetch succeeds and is cached."""
    client = AmadeusFlightClient(
        api_key=os.environ["AMADEUS_API_KEY"],
        api_secret=os.environ["AMADEUS_API_SECRET"],
        base_url="https://test.api.amadeus.com",
    )
    token1 = await client._get_token()
    token2 = await client._get_token()
    assert token1 == token2  # cache hit


@pytest.mark.asyncio
async def test_real_search_returns_results() -> None:
    """Real search on a known Amadeus test-env route returns ≥1 result."""
    # MAD→BCN is a reliable test-env route per Amadeus sandbox docs
    ...
```

### Anti-Patterns to Avoid

- **pybreaker @decorator on async functions:** The decorator wraps the coroutine object synchronously. Exceptions from `await`ed code never reach the breaker's failure counter. Use `_call_with_breaker()` helper instead.
- **httpx or requests for outbound HTTP:** ADR-008 mandates pyreqwest. Never use `aiohttp`, `httpx`, or `requests` for Amadeus calls.
- **Token in global state or module variable:** Token must live on the client instance. Multiple `AmadeusFlightClient` instances (e.g., in tests) must each have their own token cache.
- **Raising RetryError instead of original exception:** Always use `reraise=True` in the tenacity decorator. Without it, all exhausted retries raise `tenacity.RetryError` — not `APITimeoutError` or `APIServerError` — breaking the error hierarchy.
- **Blocking the event loop with sync pybreaker.call():** Do not wrap `asyncio.run()` inside `breaker.call()` to call an async function synchronously. This blocks the event loop. Always use the `_call_with_breaker()` async pattern.
- **Hardcoding "test" credentials in any test file:** Use `os.environ["AMADEUS_API_KEY"]` with the pytest `skipif` guard.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exponential backoff + retry | Custom `asyncio.sleep` loop with counter | `tenacity @retry` | Handles retryable predicate, attempt counting, reraise, and `__wrapped__` correctly |
| Circuit breaker state machine | Custom open/closed/half-open flags | `pybreaker.CircuitBreaker` | Half-open recovery logic is subtle; pybreaker's state machine is tested |
| OAuth2 client_credentials | Custom token request + parse | `pyreqwest` + simple dict access | Token response is simple JSON — no need for an OAuth library |
| HTTP connection pooling | Manual session management | `ClientBuilder().build()` as context manager | pyreqwest handles pool lifecycle; reconnects automatically |
| Form-encoded POST body | `urllib.parse.urlencode` + `body_text` | `.form({"key": "val"})` | pyreqwest's `.form()` sets `Content-Type: application/x-www-form-urlencoded` automatically (verified) |

**Key insight:** The retry + circuit breaker composition is the subtlest part. The ordering matters: retry wraps the breaker call, so each retry attempt checks the circuit state. If the breaker opens after `fail_max` failures, subsequent retries see `CircuitBreakerError` immediately — but `CircuitBreakerError` is NOT an `APIError`, so tenacity's `retry_if_exception` predicate returns False and the error propagates without further retries. This is correct behavior.

---

## Common Pitfalls

### Pitfall 1: Amadeus Sandbox Has Sparse Route Coverage

**What goes wrong:** A real `search` call returns 0 results for many origin/destination pairs in the test environment.

**Why it happens:** The Amadeus test sandbox (`test.api.amadeus.com`) has limited route data. Not all routes are available.

**How to avoid:** Use `MAD→BCN` (Madrid to Barcelona) or `LON→NYC` (London to New York) in e2e tests. These are reliably present in the Amadeus sandbox. Assert `≥1 result` not `== N results`.

**Warning signs:** 0 results returned without an HTTP error; `FlightSearchResult.count == 0`.

### Pitfall 2: Amadeus `departure.at` Has No Timezone

**What goes wrong:** `datetime.fromisoformat("2024-11-01T08:00:00")` returns a naive datetime. Assigning it to `FlightEndpoint.at` passes Pydantic validation (the field type is `datetime`, not `datetime[tz]`), but downstream comparisons with timezone-aware datetimes (e.g., `Flight.departure > datetime.now(UTC)`) raise `TypeError`.

**Why it happens:** Amadeus returns local times without TZ offset. The Phase 4.6 test fixture used TZ-aware strings specifically to test the normalizer correctly.

**How to avoid:** In `normalize_amadeus_offer()`, after `datetime.fromisoformat(seg["departure"]["at"])`, check `dt.tzinfo is None` and attach UTC as a safe fallback: `dt.replace(tzinfo=UTC)`. Document this as a known limitation (airport local time → UTC offset lookup is Phase 8 territory).

**Warning signs:** `FlightEndpoint.at.tzinfo is None`; `TypeError: can't compare offset-naive and offset-aware datetimes`.

### Pitfall 3: Amadeus 429 Does Not Include Retry-After

**What goes wrong:** Code that reads `response.headers["Retry-After"]` raises `KeyError`.

**Why it happens:** Amadeus sandbox 429 responses do not consistently include a `Retry-After` header (per D-11 and ADR-009 deferral).

**How to avoid:** Do not parse `Retry-After`. Use tenacity's fixed `wait_exponential` only. Phase 8 can add Retry-After support when production traffic patterns are known.

### Pitfall 4: pybreaker @decorator Does Not Trip on Async Functions

**What goes wrong:** Circuit never opens even after `fail_max` consecutive failures from an async client method.

**Why it happens:** `@cb` on `async def search(...)` wraps the function and calls `self.call(func, ...)`. `self.call()` invokes `func(...)` which — being an async function — returns a coroutine object, not the awaited result. No exception is raised synchronously, so pybreaker sees a "success" for every call.

**How to avoid:** Always use the `_call_with_breaker()` helper pattern (see Code Examples above). Never use `@cb` directly on async methods.

**Warning signs:** `cb.fail_counter` stays 0 even after exceptions; `cb.current_state` stays `"closed"` after deliberate failures.

### Pitfall 5: tenacity `reraise=False` (default) Wraps Exceptions in RetryError

**What goes wrong:** After all retries are exhausted, callers catch `tenacity.RetryError` instead of `APITimeoutError` / `APIServerError`. The error hierarchy and `retryable` flag are lost.

**Why it happens:** Default tenacity behavior. `reraise` defaults to `False`.

**How to avoid:** Always set `reraise=True` in the `retry()` call. Verified in research: `RetryError` is NOT raised when `reraise=True`.

### Pitfall 6: Airport Code vs City Code in Amadeus `locations` Dict

**What goes wrong:** `dictionaries["locations"]["LON"]` raises `KeyError` — the key is `"LHR"` (airport code), not `"LON"` (city code).

**Why it happens:** Amadeus uses IATA airport codes (e.g., `LHR`, `CDG`) as keys in `dictionaries.locations`, but may return city codes in the flight segment `iataCode` field depending on how the search request was parameterized.

**How to avoid:** Use `.get(iata_code, {})` with a fallback to the IATA code itself when `cityCode` is absent (already done in the existing `normalize_amadeus_offer()`). Do not assume the key exists.

### Pitfall 7: asyncio.Lock Must Be Instance Variable, Not Class Variable

**What goes wrong:** Concurrent requests from different tests share the same token lock, causing test interference.

**Why it happens:** If `_token_lock = asyncio.Lock()` is a class variable rather than an instance variable, all `AmadeusFlightClient` instances share the same lock object.

**How to avoid:** Always initialize `self._token_lock = asyncio.Lock()` inside `__init__`. Verified: `asyncio.Lock()` must be created in the same event loop context it will be used in — creating it at class definition time (before the event loop starts) may fail in some asyncio versions.

---

## Code Examples

### Amadeus OAuth2 Token Request (verified against docs)

```python
# Source: developers.amadeus.com/self-service/apis-docs/guides/authorization
# POST https://test.api.amadeus.com/v1/security/oauth2/token
# Content-Type: application/x-www-form-urlencoded
# Body: grant_type=client_credentials&client_id=<KEY>&client_secret=<SECRET>

# Response shape:
{
    "type": "amadeusOAuth2Token",
    "access_token": "Application Access Token",
    "token_type": "Bearer",
    "expires_in": 1799,
    "state": "approved",
    "scope": ""
}

# pyreqwest form POST verified:
resp = await (
    client.post(token_url)
    .form({"grant_type": "client_credentials", "client_id": key, "client_secret": secret})
    .build()
    .send()
)
# Sets Content-Type: application/x-www-form-urlencoded (verified in research)
```

### Amadeus Flight Offers Search v2 (ASSUMED: based on SDK and test fixture)

```python
# GET https://test.api.amadeus.com/v2/shopping/flight-offers
# Headers: Authorization: Bearer <token>
# Query params:
{
    "originLocationCode": "MAD",       # required
    "destinationLocationCode": "BCN",  # required
    "departureDate": "2024-11-01",     # required, YYYY-MM-DD
    "adults": "1",                     # required
    "max": "5",                        # optional, max results
    "currencyCode": "USD",             # optional
    "travelClass": "ECONOMY",          # optional: ECONOMY | PREMIUM_ECONOMY | BUSINESS | FIRST
    "nonStop": "false",                # optional
}

# Response: {"data": [<FlightOffer>...], "dictionaries": {"carriers": {...}, "locations": {...}}}
```

### Concurrent Token Refresh (double-checked locking)

```python
# Source: asyncio.Lock docs + D-01 pattern
async def _get_token(self) -> str:
    now = datetime.now(UTC)
    if self._access_token and now < self._expires_at - timedelta(seconds=60):
        return self._access_token  # fast path

    async with self._token_lock:               # serialize refreshes
        now = datetime.now(UTC)
        if self._access_token and now < self._expires_at - timedelta(seconds=60):
            return self._access_token          # another coroutine already refreshed
        return await self._refresh_token()     # only one refresh fires
```

### pyreqwest Bearer Auth (verified against test suite)

```python
# Source: github.com/MarkusSintonen/pyreqwest test suite
resp = await (
    client.get(url)
    .bearer_auth(token)          # Authorization: Bearer <token>
    .query({"key": "val"})       # URL query params
    .build()
    .send()
)
body = await resp.json()
```

### pyreqwest Status Code from StatusError (verified)

```python
# Source: verified in research with pyreqwest 0.12.0
from pyreqwest.exceptions import StatusError

try:
    ...
except StatusError as exc:
    status = exc.details["status"]   # e.g. 429, 500, 401
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-rolled `asyncio.sleep` retry loop | `tenacity @retry` with `reraise=True` | Phase 7 | Less code, correct semantics, `__wrapped__` introspection preserved |
| No circuit breaker | `pybreaker.CircuitBreaker` with manual async wrapper | Phase 7 | Prevents thundering herd on Amadeus outages |
| `MockFlightAPIClient` at startup | Conditional `AmadeusFlightClient` / `MockFlightAPIClient` based on env + creds | Phase 7 | Real data without breaking local dev |

**Deprecated/outdated:**
- `backend/app/tools/retry.py` internal implementation: The `asyncio.sleep` loop and `for attempt in range(max_retries + 1)` pattern is replaced by tenacity internals. The public `retry_on_failure()` function signature and behavior is preserved.
- `search_flights._flight_client` attribute injection: Closed in Phase 5 (PydanticAI RunContext). NOT relevant to this phase — `flight_client` is now in `ChatDeps` threaded via `RunContext`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Amadeus Flight Offers Search v2 endpoint is `GET /v2/shopping/flight-offers` | Standard Stack, Code Examples | 404 on all search calls; fix is trivial (check docs) |
| A2 | Amadeus test environment route `MAD→BCN` reliably returns ≥1 result | Common Pitfalls 1, e2e test pattern | e2e test fails intermittently; switch to a different known route |
| A3 | Amadeus `departure.at` in test environment is always naive local datetime (no TZ offset) | Common Pitfalls 2 | Timezone handling branch never exercised; no functional bug |
| A4 | Amadeus prod base URL is `https://api.amadeus.com` | Standard Stack, Lifespan pattern | Auth/search fails in prod mode; fix is one-line URL change |
| A5 | `pybreaker.CircuitBreaker(throw_new_error_on_trip=True)` is required for `CircuitBreakerError` to be raised on trip | Circuit breaker pattern | Without it, pybreaker re-raises the original exception rather than `CircuitBreakerError` when tripping — changes the error type at the boundary |

---

## Open Questions

1. **Token 401 handling requires cache invalidation**
   - What we know: Amadeus returns 401 when the token is expired or malformed. The error mapping raises `APIClientError(retryable=False)`.
   - What's unclear: With `retryable=False`, tenacity will not retry the 401. But the root cause may be a stale cached token (clock skew, early invalidation by Amadeus). Should 401 force token cache invalidation + one retry?
   - Recommendation: On 401, set `self._access_token = None` and `self._expires_at = datetime.min` before raising `APIClientError(retryable=True)`. The next retry fetches a fresh token. Cap this at 1 retry to avoid infinite 401 loops.

2. **`_handle_error` is a "protected" pybreaker method (single underscore)**
   - What we know: The `_call_with_breaker()` pattern accesses `state._handle_error()`.
   - What's unclear: pybreaker may change this API in future versions.
   - Recommendation: Pin `pybreaker>=1.4.1,<2.0` and add a comment explaining why we access the internal method. Alternative: use the `calling()` context manager if pybreaker adds async support in a future release.

3. **`throw_new_error_on_trip` default value**
   - What we know: `CircuitBreaker(throw_new_error_on_trip=True)` is needed for `CircuitBreakerError` to be raised when the circuit first opens.
   - What's unclear: Whether the default is True or False (constructor signature not fully inspected).
   - Recommendation: Always pass `throw_new_error_on_trip=True` explicitly to ensure consistent behavior regardless of defaults.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | compose-up for Postgres (phase depends on Phase 6) | ✓ | 28.5.1 | — |
| Python 3.13 | uv venv | ✓ | 3.13.9 | — |
| uv | Package management | ✓ | 0.9.10 | — |
| AMADEUS_API_KEY | Real-API e2e tests | ✗ | — | Auto-fallback to mock (D-05); e2e_amadeus tests skipif |
| AMADEUS_API_SECRET | Real-API e2e tests | ✗ | — | Same as above |

**Missing dependencies with no fallback:** None — all blocking deps are available.

**Missing dependencies with fallback:** AMADEUS_* credentials not present in local dev environment; auto-fallback to MockFlightAPIClient is the designed behavior (D-05).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && uv run pytest tests/unit/test_retry.py -x` |
| Full suite command | `cd backend && uv run pytest tests/unit tests/integration --cov=app --cov-fail-under=60` |
| Amadeus real-API suite | `cd backend && uv run pytest tests/e2e_amadeus/ -v -s` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-real-flight-api | tenacity replaces retry.py; existing call sites unchanged | unit | `uv run pytest tests/unit/test_retry.py -x` | ✅ exists (needs update) |
| REQ-real-flight-api | AmadeusFlightClient maps Amadeus offer to FlightResult | unit | `uv run pytest tests/unit/test_amadeus_client.py -x` | ❌ Wave 0 |
| REQ-real-flight-api | Token cache: concurrent callers get same token (single refresh) | unit | `uv run pytest tests/unit/test_amadeus_token_cache.py -x` | ❌ Wave 0 |
| REQ-real-flight-api | pybreaker trips after fail_max async failures | unit | `uv run pytest tests/unit/test_circuit_breaker.py -x` | ❌ Wave 0 |
| REQ-real-flight-api | HTTP error → APIError mapping (401→APIClientError, 429→APIRateLimitError, 5xx→APIServerError) | unit | `uv run pytest tests/unit/test_amadeus_error_mapping.py -x` | ❌ Wave 0 |
| REQ-real-flight-api | Lifespan auto-fallback: missing creds → MockFlightAPIClient + WARN log | integration | `uv run pytest tests/integration/test_health.py -x` | ✅ exists (extend) |
| REQ-real-flight-api | /health returns flight_provider field | integration | `uv run pytest tests/integration/test_health.py::test_health_includes_flight_provider -x` | ❌ Wave 0 |
| REQ-real-flight-api | Real token fetch + cache hit | e2e_amadeus | `uv run pytest tests/e2e_amadeus/test_amadeus_client.py::test_token_fetch_and_cache` | ❌ Wave 0 |
| REQ-real-flight-api | Real search MAD→BCN returns ≥1 result | e2e_amadeus | `uv run pytest tests/e2e_amadeus/test_amadeus_client.py::test_real_search_returns_results` | ❌ Wave 0 |
| REQ-real-flight-api | Full vendor-neutral shape after real normalization | e2e_amadeus | `uv run pytest tests/e2e_amadeus/test_amadeus_client.py::test_vendor_neutral_shape` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && uv run pytest tests/unit/ -x --tb=short`
- **Per wave merge:** `cd backend && uv run pytest tests/unit tests/integration --cov=app --cov-fail-under=60`
- **Phase gate:** Full suite green before `/gsd:verify-work`; `e2e_amadeus` tests run separately with AMADEUS_* secrets

### Wave 0 Gaps

- [ ] `tests/unit/test_amadeus_client.py` — unit tests for normalize/map/error-mapping (no real HTTP)
- [ ] `tests/unit/test_amadeus_token_cache.py` — concurrent token refresh with `asyncio.Lock`
- [ ] `tests/unit/test_circuit_breaker.py` — pybreaker async-safe pattern: fail_max trips, `_call_with_breaker` behavior
- [ ] `tests/e2e_amadeus/__init__.py` + `tests/e2e_amadeus/conftest.py` + `tests/e2e_amadeus/test_amadeus_client.py` — real-API tests with `pytestmark = pytest.mark.skipif(not AMADEUS_AVAILABLE, ...)` guard
- [ ] Update `tests/unit/test_retry.py` — existing 8 tests should pass unchanged after tenacity replacement; add regression test for `RetryError` not escaping (reraise=True)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | OAuth2 client_credentials; bearer token in Authorization header; `SecretStr` in Settings |
| V3 Session Management | no | Token lifecycle is process-internal, not HTTP session |
| V4 Access Control | no | Flight search is auth-gated via existing JWT middleware; no new access control |
| V5 Input Validation | yes | IATA codes validated in `FlightQuery`; query params type-checked via pydantic |
| V6 Cryptography | no | Token transport via HTTPS to Amadeus; no custom crypto |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leakage in logs | Information Disclosure | `pydantic.SecretStr` for `amadeus_api_key`/`amadeus_api_secret`; `ApiKeyScrubber` already installed at startup |
| Credential in error message | Information Disclosure | Wrap token refresh errors with generic message, not raw exception string containing the secret |
| SSRF via base_url | Tampering | `amadeus_env` is a `Literal["test","prod","mock"]` — no user-controlled URL injection possible (unlike provider probes in Phase 4.5) |
| 401 token loop | Denial of Service | Cap 401-triggered token refresh retries at 1 (Open Question 1) |

---

## Sources

### Primary (HIGH confidence)

- `07-CONTEXT.md` — locked decisions D-01 through D-15
- `backend/app/tools/retry.py` — hand-rolled retry public API (to be preserved)
- `backend/app/exceptions.py` — APIError hierarchy with `retryable` flag
- `backend/app/flights/models.py` — vendor-neutral target models
- `backend/app/tools/flight_search.py` — `normalize_amadeus_offer()` already implements Amadeus field mapping
- `backend/tests/unit/test_tool_json_normalization.py` — Amadeus fixture shape confirmed
- Live pyreqwest 0.12.0 test (installed in venv): `.form()`, `.bearer_auth()`, `StatusError.details["status"]`, exception hierarchy
- Live tenacity 9.1.2 test: `@retry` on async functions, `retry_if_exception`, `reraise=True`, call_count=1 for non-retryable
- Live pybreaker 1.4.1 test: `@decorator` async failure (NOT working), `state._handle_error()` async pattern (working, trips at fail_max=2)
- [CITED: developers.amadeus.com/self-service/apis-docs/guides/authorization] — token endpoint URL, request format, response shape
- [CITED: github.com/MarkusSintonen/pyreqwest] — builder API, `.form()`, `.bearer_auth()`, exception types
- [CITED: tenacity.readthedocs.io] — `@retry`, `stop_after_attempt`, `wait_exponential`, `AsyncRetrying`
- [CITED: github.com/danielfm/pybreaker] — `CircuitBreaker`, `call_async`, `CircuitBreakerError`, state machine

### Secondary (MEDIUM confidence)

- PyPI JSON API for tenacity 9.1.4, pybreaker 1.4.1, pyreqwest 0.12.0 — version dates confirmed
- Amadeus Python SDK README (github.com/amadeus4dev/amadeus-python) — confirms endpoint `/v2/shopping/flight-offers-search` and parameter names

### Tertiary (LOW confidence)

- [ASSUMED] Amadeus Flight Offers Search v2 endpoint path is `/v2/shopping/flight-offers` (direct HTTP) — derived from SDK wrapper + test fixture field names; Amadeus docs page did not load during research
- [ASSUMED] Amadeus prod base URL is `https://api.amadeus.com` — standard Amadeus convention; test URL confirmed from docs
- [ASSUMED] MAD→BCN is a reliable sandbox route — community-known sandbox behavior, not officially documented

---

## Metadata

**Confidence breakdown:**
- Standard stack (pyreqwest, tenacity, pybreaker): HIGH — all three packages verified on PyPI, slopcheck passed, live API tested in venv
- Architecture / implementation patterns: HIGH — all patterns verified via live code execution in research session
- Amadeus API request shape: HIGH for token endpoint (official docs), MEDIUM for search endpoint (SDK inference + test fixture verification)
- Common pitfalls: HIGH — pybreaker async bug verified live; datetime TZ pitfall confirmed from existing code comment in flight_search.py
- Test gating / CI patterns: HIGH — existing CI workflow reviewed; path-based test discovery confirmed from justfile and CLAUDE.md

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (pyreqwest is Beta-stage; check for breaking changes before planning if >2 weeks elapse)

---

## RESEARCH COMPLETE
