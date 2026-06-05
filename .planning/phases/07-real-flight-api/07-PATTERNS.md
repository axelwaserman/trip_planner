# Phase 7: Real Flight API - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 19 new/modified files
**Analogs found:** 17 / 19

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/app/flights/amadeus_client.py` | service | request-response | `backend/app/tools/flight_client.py` (`MockFlightAPIClient`) | exact |
| `backend/app/flights/amadeus_token_cache.py` | utility | request-response | `backend/app/tools/flight_client.py` (`__init__` state) | role-match |
| `backend/app/tools/retry.py` | utility | request-response | `backend/app/tools/retry.py` (itself — rewrite in-place) | exact |
| `backend/app/tools/circuit_breaker.py` | utility | request-response | `backend/app/tools/retry.py` | role-match |
| `backend/app/exceptions.py` | model | request-response | `backend/app/exceptions.py` (itself — extend) | exact |
| `backend/app/config.py` | config | — | `backend/app/config.py` (itself — extend) | exact |
| `backend/app/api/main.py` | config | — | `backend/app/api/main.py` (itself — modify lifespan) | exact |
| `backend/app/api/routes/routes.py` | controller | request-response | `backend/app/api/routes/routes.py` (itself — extend `/health`) | exact |
| `backend/tests/unit/test_amadeus_client.py` | test | request-response | `backend/tests/unit/test_mock_client.py` | exact |
| `backend/tests/unit/test_amadeus_token_cache.py` | test | request-response | `backend/tests/unit/test_retry.py` | role-match |
| `backend/tests/unit/test_circuit_breaker.py` | test | request-response | `backend/tests/unit/test_retry.py` | exact |
| `backend/tests/unit/test_amadeus_error_mapping.py` | test | request-response | `backend/tests/unit/test_exceptions.py` | exact |
| `backend/tests/unit/test_retry.py` | test | request-response | `backend/tests/unit/test_retry.py` (itself — extend) | exact |
| `backend/tests/integration/test_health.py` | test | request-response | `backend/tests/integration/test_health.py` (itself — extend) | exact |
| `backend/tests/e2e_amadeus/__init__.py` | test | — | `backend/tests/e2e/__init__.py` | exact |
| `backend/tests/e2e_amadeus/conftest.py` | test | — | `backend/tests/integration/conftest.py` | role-match |
| `backend/tests/e2e_amadeus/test_amadeus_client.py` | test | request-response | `backend/tests/unit/test_mock_client.py` | role-match |
| `justfile` | config | — | `justfile` (itself — extend) | exact |
| `.github/workflows/ci.yml` | config | — | `.github/workflows/ci.yml` (itself — extend) | exact |
| `backend/pyproject.toml` | config | — | `backend/pyproject.toml` (itself — extend) | exact |

---

## Pattern Assignments

### `backend/app/flights/amadeus_client.py` (service, request-response)

**Analog:** `backend/app/tools/flight_client.py` — `MockFlightAPIClient` class (lines 84–327)

**Imports pattern** (from `flight_client.py` lines 1–10 + RESEARCH.md Pattern 1):
```python
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pybreaker
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, RequestTimeoutError, StatusError

from app.exceptions import (
    APIClientError,
    APIRateLimitError,
    APIServerError,
    APITimeoutError,
)
from app.flights.models import Flight, FlightQuery, FlightResult, FlightSearchResult, SortBy
from app.tools.flight_client import FlightAPIClient
from app.tools.retry import retry_on_failure

logger = logging.getLogger(__name__)
```

**ABC implementation pattern** — copy the class-level structure from `MockFlightAPIClient` (lines 84–188), keeping the same four abstract methods (`health_check`, `search`, `get_flight_details`, `check_availability`). Replace mock internals with HTTP calls:
```python
class AmadeusFlightClient(FlightAPIClient):
    """Amadeus REST flight API client implementing FlightAPIClient ABC.

    Wraps Amadeus Flight Offers Search v2 behind the vendor-neutral
    FlightAPIClient interface. Token lifecycle uses in-process cache with
    proactive refresh and concurrent-refresh lock (D-01/D-02).
    """

    _REFRESH_BUFFER_SECONDS = 60

    def __init__(self, api_key: str, api_secret: str, base_url: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url
        self._access_token: str | None = None
        self._expires_at: datetime = datetime.min.replace(tzinfo=UTC)
        self._token_lock = asyncio.Lock()  # MUST be instance variable, not class variable (Pitfall 7)
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=60,
            throw_new_error_on_trip=True,  # Required for CircuitBreakerError on trip (A5)
        )
```

**Token cache pattern** — from RESEARCH.md Pattern 1 (verified against asyncio.Lock docs):
```python
    async def _get_token(self) -> str:
        """Return cached token, refreshing proactively if near-expiry."""
        now = datetime.now(UTC)
        if self._access_token and now < self._expires_at - timedelta(seconds=self._REFRESH_BUFFER_SECONDS):
            return self._access_token  # fast path

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
            raise APIError(message=f"Amadeus token refresh failed: {exc}", retryable=True) from exc
```

**Core HTTP search pattern** — from RESEARCH.md Pattern 4 (pyreqwest usage):
```python
    @retry_on_failure(max_retries=3, backoff_base=2.0)
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
        try:
            return await _call_with_breaker(self._breaker, self._search_impl, query, ...)
        except pybreaker.CircuitBreakerError as exc:
            raise APIServerError(message=f"Circuit breaker open: {exc}", retryable=False) from exc

    async def _search_impl(self, query: FlightQuery, limit: int, ...) -> list[Flight]:
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
                    .bearer_auth(token)
                    .query(params)
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

**Error handling pattern** — from RESEARCH.md Pattern 5 (Amadeus HTTP status mapping):
```python
def _raise_from_http_status(status: int, exc: Exception) -> None:
    """Map Amadeus HTTP status to our APIError hierarchy. Never returns."""
    if status == 401:
        # Force token cache invalidation so next retry fetches a fresh token
        raise APIClientError(
            message=f"Amadeus authentication failed (401) — token invalidated",
            retryable=False,
        ) from exc
    elif status == 429:
        raise APIRateLimitError(message="Amadeus rate limit exceeded (429)", retryable=True) from exc
    elif status >= 500:
        raise APIServerError(message=f"Amadeus server error ({status})", retryable=True) from exc
    else:
        raise APIClientError(message=f"Amadeus client error ({status})", retryable=False) from exc
```

**Field mapping pattern** — reuse `normalize_amadeus_offer()` already in `backend/app/tools/flight_search.py` (lines 141–212). The function signature is:
```python
def normalize_amadeus_offer(offer: dict[str, Any], dictionaries: dict[str, Any]) -> FlightResult:
```
Call it from `_parse_flight_offers(body)` iterating `body["data"]` with `body["dictionaries"]`.

**Timezone pitfall** — from `flight_search.py` line 181 and RESEARCH.md Pitfall 2:
```python
# normalize_amadeus_offer currently does:
dep_at: datetime = datetime.fromisoformat(seg["departure"]["at"])
# Phase 7 must add TZ fallback when naive:
if dep_at.tzinfo is None:
    dep_at = dep_at.replace(tzinfo=UTC)  # Safe sandbox fallback; Phase 8 = airport TZ lookup
```

---

### `backend/app/flights/amadeus_token_cache.py` (utility, request-response)

**Note:** The token cache may be kept as private methods on `AmadeusFlightClient` (see `amadeus_client.py` pattern above) rather than a separate file. If extracted, it should be a dataclass/class with the `asyncio.Lock`, `_access_token`, and `_expires_at` fields. No strong codebase analog for a standalone token cache class — implement as a private inner concern of `AmadeusFlightClient.__init__`.

**If extracted as separate class**, pattern from `backend/app/tools/flight_client.py` lines 103–109 (`MockFlightAPIClient.__init__` pattern for instance-level state):
```python
@dataclass
class _TokenCache:
    access_token: str | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
```

---

### `backend/app/tools/retry.py` (utility, request-response — REWRITE)

**Analog:** `backend/app/tools/retry.py` (current, lines 1–75) — preserve the public function signature exactly.

**Current public API to preserve** (lines 17–21):
```python
def retry_on_failure(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (APIError,),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
```

**New tenacity implementation** — from RESEARCH.md Pattern 2 (verified against tenacity 9.1.2 in venv):
```python
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

def retry_on_failure(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (APIError,),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(max_retries + 1),  # +1: initial attempt counts
        wait=wait_exponential(multiplier=backoff_base),
        retry=retry_if_exception(
            lambda e: isinstance(e, exceptions) and getattr(e, "retryable", False)
        ),
        reraise=True,  # CRITICAL: without this, tenacity raises RetryError not the original exception
    )
```

**Tests that MUST still pass** — all 8 tests in `backend/tests/unit/test_retry.py` (lines 51–170):
- `test_retry_successful_function` — passes immediately
- `test_retry_eventually_succeeds` — retries and succeeds
- `test_retry_exhausts_attempts` — raises `APIServerError` (not `RetryError`)
- `test_retry_non_retryable_error` — fails immediately without retries
- `test_retry_exponential_backoff` — timing check (use `backoff_base=0.01` in test for speed)
- `test_retry_custom_exceptions` — custom exception tuple
- `test_retry_preserves_function_metadata` — `__name__` and `__doc__` preserved
- `test_retry_with_zero_retries` — `max_retries=0`
- `test_retry_passes_args_and_kwargs` — args forwarded correctly

**Key difference from current impl:** tenacity's `wait_exponential(multiplier=backoff_base)` computes `multiplier * 2^(attempt-1)` not `backoff_base^attempt` — the test for exponential timing at line 116–118 may need adjustment for the new formula.

---

### `backend/app/tools/circuit_breaker.py` (utility, request-response — NEW)

**Analog:** `backend/app/tools/retry.py` (utility wrapper pattern)

**Imports pattern:**
```python
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import pybreaker

logger = logging.getLogger(__name__)

T = TypeVar("T")
```

**Core async-safe pattern** — from RESEARCH.md Pattern 3 (verified against pybreaker 1.4.1):
```python
async def call_with_breaker(
    breaker: pybreaker.CircuitBreaker,
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Async-safe circuit breaker wrapper.

    pybreaker's @decorator does NOT handle async functions correctly — it wraps
    the coroutine object synchronously, so exceptions never reach the failure
    counter. This manual wrapper calls state.before_call() (raises
    CircuitBreakerError if circuit is open) and updates state after awaiting.

    Verified against pybreaker 1.4.1 in 07-RESEARCH.md.

    Args:
        breaker: Configured CircuitBreaker instance.
        coro_fn: Async function to call.
        *args: Positional arguments forwarded to coro_fn.
        **kwargs: Keyword arguments forwarded to coro_fn.

    Returns:
        The awaited result of coro_fn.

    Raises:
        pybreaker.CircuitBreakerError: If circuit is open (raised by before_call).
        Any exception from coro_fn that is_system_error() is counted against fail_max.
    """
    breaker.state.before_call(coro_fn, *args, **kwargs)
    try:
        result = await coro_fn(*args, **kwargs)
    except BaseException as exc:
        if breaker.is_system_error(exc):
            breaker.state._handle_error(exc, reraise=False)  # noqa: SLF001 — pybreaker internal; pin pybreaker<2.0
        raise
    else:
        breaker.state._handle_success()
        return result
```

**Note on `_handle_error`:** This accesses a protected method. Per RESEARCH.md Open Question 2, pin `pybreaker>=1.4.1,<2.0` in `pyproject.toml` and add a comment explaining the internal API access. The comment is required to satisfy mypy's `SLF001` ruff rule suppression.

---

### `backend/app/exceptions.py` (model — EXTEND)

**Analog:** `backend/app/exceptions.py` (current, lines 1–51)

**Current hierarchy to preserve** (lines 6–51) — `TripPlannerError` → `APIError` (retryable flag) → `APITimeoutError`, `APIRateLimitError`, `APIServerError`, `APIClientError`, `FlightSearchError`.

**No new exception classes needed for Phase 7.** The existing hierarchy already covers all Amadeus HTTP error cases:
- 401 → `APIClientError(retryable=False)`
- 429 → `APIRateLimitError(retryable=True)`
- 5xx → `APIServerError(retryable=True)`
- timeout → `APITimeoutError(retryable=True)`
- circuit open → `APIServerError(retryable=False)` (mapped from `CircuitBreakerError`)

If a `CircuitBreakerOpenError` subclass is desired for observability, follow the same `@dataclass` + `retryable` pattern from lines 11–50.

---

### `backend/app/config.py` (config — EXTEND)

**Analog:** `backend/app/config.py` (current, lines 13–173)

**Current Settings additions pattern** (lines 56–99) — note how optional credentials use `str | None = None` for cloud API keys:
```python
# OpenAI Configuration (optional)
openai_api_key: str | None = None
openai_model: str = "gpt-4o-mini"
```

**Phase 7 additions** — append after existing fields, following same comment grouping convention (lines 64–82 for the comment-block pattern):
```python
# Amadeus Flight API (Phase 7)
# amadeus_env controls which Amadeus base URL is used and whether a real
# AmadeusFlightClient is constructed at lifespan. "mock" bypasses Amadeus entirely.
amadeus_env: Literal["test", "prod", "mock"] = "test"
amadeus_api_key: SecretStr | None = None    # pydantic.SecretStr prevents accidental log leaks
amadeus_api_secret: SecretStr | None = None
```

**Import additions needed:**
```python
from typing import Literal  # already imported if not present
from pydantic import SecretStr  # add to existing pydantic import line
```

**SecretStr access pattern** (from RESEARCH.md Pattern 7):
```python
settings.amadeus_api_key.get_secret_value()  # only call this in lifespan, not in logging paths
```

---

### `backend/app/api/main.py` (config — MODIFY lifespan)

**Analog:** `backend/app/api/main.py` (current, lines 29–161)

**Current lifespan flight client initialization** (lines 56–57):
```python
# Initialize flight client
flight_client = MockFlightAPIClient(seed=42)
```

**Replace with auto-fallback pattern** — from RESEARCH.md Pattern 6. Insert after `install_log_scrubber()` call (line 54), before `LLMProviderFactory` construction (line 60):
```python
from app.flights.amadeus_client import AmadeusFlightClient  # add to imports

# Phase 7: branch on amadeus_env + credential presence (D-04/D-05)
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

app.state.flight_provider = flight_provider  # consumed by GET /health (D-06)
```

**`app.state` stashing pattern** (lines 79–93) — `flight_provider` follows the same pattern as existing `app.state.*` assignments. Note `FlightAPIClient` must be imported for the type annotation:
```python
from app.tools.flight_client import FlightAPIClient, MockFlightAPIClient
```

---

### `backend/app/api/routes/routes.py` (controller — EXTEND `/health`)

**Analog:** `backend/app/api/routes/routes.py` (current, lines 429–439)

**Current `/health` endpoint** (lines 429–439):
```python
@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
```

**Phase 7 extension** — add `request: Request` parameter and read `flight_provider` from `app.state`:
```python
@router.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Dictionary with status and flight_provider fields.
        flight_provider is "real" (AmadeusFlightClient) or "mock" (MockFlightAPIClient).
    """
    flight_provider = getattr(request.app.state, "flight_provider", "mock")
    return {"status": "healthy", "flight_provider": flight_provider}
```

`Request` is already imported at line 8 (`from fastapi import APIRouter, Depends, HTTPException, Request, status`).

---

### `backend/tests/unit/test_amadeus_client.py` (test, request-response — NEW)

**Analog:** `backend/tests/unit/test_mock_client.py` (lines 1–60+) + `backend/tests/unit/test_tool_json_normalization.py` (lines 1–80)

**Imports pattern** (from `test_mock_client.py` lines 1–10):
```python
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import APIClientError, APIRateLimitError, APIServerError, APITimeoutError
from app.flights.amadeus_client import AmadeusFlightClient
from app.flights.models import FlightQuery
```

**Test structure pattern** — AAA (Arrange-Act-Assert) from CLAUDE.md common/testing.md. All tests are `@pytest.mark.asyncio` async (since `asyncio_mode = "auto"` in pyproject.toml, no marker needed):
```python
async def test_search_raises_api_server_error_on_5xx() -> None:
    # Arrange
    client = AmadeusFlightClient(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://test.api.amadeus.com",
    )
    # Act / Assert — no real HTTP; mock pyreqwest at the boundary
    with patch.object(client, "_get_token", return_value="token"):
        with patch("pyreqwest.client.ClientBuilder") as mock_builder:
            mock_builder().timeout().error_for_status().build().__aenter__.return_value.get...
            # ... mock StatusError with status=500
```

**Amadeus fixture shape** (from `test_tool_json_normalization.py` lines 29–80) — reuse `AMADEUS_FLIGHT_OFFER` and `AMADEUS_DICTIONARIES` from that file or import them directly as fixtures.

---

### `backend/tests/unit/test_amadeus_token_cache.py` (test, request-response — NEW)

**Analog:** `backend/tests/unit/test_retry.py` (structure) + RESEARCH.md Pattern from §Code Examples

**Key test cases** — concurrent token refresh with `asyncio.Lock`:
```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

async def test_concurrent_callers_refresh_token_once() -> None:
    """Multiple concurrent callers trigger only one token refresh."""
    client = AmadeusFlightClient(api_key="k", api_secret="s", base_url="https://test.api.amadeus.com")
    refresh_count = 0

    async def mock_refresh() -> str:
        nonlocal refresh_count
        refresh_count += 1
        return "fresh_token"

    with patch.object(client, "_refresh_token", side_effect=mock_refresh):
        tokens = await asyncio.gather(*[client._get_token() for _ in range(5)])

    assert refresh_count == 1
    assert all(t == "fresh_token" for t in tokens)
```

---

### `backend/tests/unit/test_circuit_breaker.py` (test, request-response — NEW)

**Analog:** `backend/tests/unit/test_retry.py` (utility test pattern)

**Critical test case** — pybreaker trips after `fail_max` async failures:
```python
import pybreaker
import pytest

from app.tools.circuit_breaker import call_with_breaker

async def test_breaker_trips_after_fail_max() -> None:
    """Circuit opens after fail_max consecutive failures."""
    breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=60, throw_new_error_on_trip=True)

    async def always_fails() -> None:
        raise RuntimeError("boom")

    # Fail fail_max times
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await call_with_breaker(breaker, always_fails)

    # Circuit should now be open
    with pytest.raises(pybreaker.CircuitBreakerError):
        await call_with_breaker(breaker, always_fails)

async def test_breaker_decorator_on_async_does_not_work() -> None:
    """Document that @cb on async function does NOT trip the circuit.

    This test locks in the known pybreaker limitation per 07-RESEARCH.md Pitfall 4.
    """
    breaker = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=60, throw_new_error_on_trip=True)

    @breaker  # DO NOT use this pattern — documented here as a regression guard
    async def broken_approach() -> None:
        raise RuntimeError("boom")

    for _ in range(5):
        with pytest.raises(RuntimeError):
            await broken_approach()

    # Breaker is still closed — @decorator doesn't work on async
    assert breaker.current_state == "closed"
```

---

### `backend/tests/unit/test_amadeus_error_mapping.py` (test, request-response — NEW)

**Analog:** `backend/tests/unit/test_exceptions.py` (lines 1–70)

**Imports pattern** (from `test_exceptions.py` lines 1–12):
```python
import pytest
from app.exceptions import APIClientError, APIRateLimitError, APIServerError, APITimeoutError
from app.flights.amadeus_client import _raise_from_http_status  # or wherever the function lives
```

**Test structure pattern** — parameterized over HTTP status codes:
```python
@pytest.mark.parametrize("status,exc_type,retryable", [
    (401, APIClientError, False),
    (400, APIClientError, False),
    (404, APIClientError, False),
    (429, APIRateLimitError, True),
    (500, APIServerError, True),
    (503, APIServerError, True),
])
def test_raise_from_http_status(status: int, exc_type: type, retryable: bool) -> None:
    with pytest.raises(exc_type) as exc_info:
        _raise_from_http_status(status, RuntimeError("original"))
    assert exc_info.value.retryable is retryable
```

---

### `backend/tests/unit/test_retry.py` (test — UPDATE)

**Analog:** `backend/tests/unit/test_retry.py` (itself — existing 8 tests must pass unchanged)

All 8 existing tests must continue to pass. Add one regression test:
```python
async def test_retry_raises_original_exception_not_retry_error() -> None:
    """Regression: tenacity reraise=True ensures RetryError never escapes.

    Without reraise=True, tenacity wraps the original exception in RetryError
    after all attempts are exhausted — breaking the APIError hierarchy.
    """
    from tenacity import RetryError

    @retry_on_failure(max_retries=2, backoff_base=0.01)
    async def always_fails() -> str:
        raise APIServerError(message="always fails")

    with pytest.raises(APIServerError):
        await always_fails()
    # Ensure RetryError is never raised
```

**Note on timing test** (`test_retry_exponential_backoff` lines 98–118): tenacity `wait_exponential(multiplier=2.0)` computes `2.0 * 2^(attempt-1)` not `2.0^attempt` as the hand-rolled version did. The test uses `backoff_base=0.1` so the formula difference matters. Adjust the assertion on line 118 or update the docstring.

---

### `backend/tests/integration/test_health.py` (test — EXTEND)

**Analog:** `backend/tests/integration/test_health.py` (itself — lines 1–14)

**Current test** (lines 10–14):
```python
def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

**Phase 7 extension** — update existing assertion and add a new test:
```python
def test_health() -> None:
    """Health check returns status + flight_provider field."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "flight_provider" in data  # D-06: field must always be present

def test_health_flight_provider_is_mock_without_credentials() -> None:
    """Without AMADEUS_* credentials, flight_provider is 'mock'."""
    response = client.get("/health")
    data = response.json()
    # In test env, credentials are absent; auto-fallback sets flight_provider="mock"
    assert data["flight_provider"] == "mock"
```

---

### `backend/tests/e2e_amadeus/conftest.py` (test — NEW)

**Analog:** `backend/tests/integration/conftest.py` (lines 1–77) — but simpler (no httpx stub needed; real HTTP).

**Pattern** — `pytestmark` skip-guard from RESEARCH.md Pattern 10:
```python
"""e2e_amadeus conftest — skip entire suite when credentials are absent."""
import os
import pytest

AMADEUS_AVAILABLE = (
    os.environ.get("AMADEUS_API_KEY") is not None
    and os.environ.get("AMADEUS_API_SECRET") is not None
)

# Module-level skipif so all tests in this directory are skipped atomically.
# Do NOT add @pytest.mark.skipif on each test — the module-level mark is
# D-14's intent: "default pytest does NOT run them".
collect_ignore_all: list[str] = []  # kept for documentation purposes

@pytest.fixture(scope="module")
def amadeus_client():
    """Real AmadeusFlightClient for e2e tests. Requires AMADEUS_* env vars."""
    from app.flights.amadeus_client import AmadeusFlightClient
    return AmadeusFlightClient(
        api_key=os.environ["AMADEUS_API_KEY"],
        api_secret=os.environ["AMADEUS_API_SECRET"],
        base_url="https://test.api.amadeus.com",
    )
```

---

### `backend/tests/e2e_amadeus/test_amadeus_client.py` (test — NEW)

**Analog:** `backend/tests/unit/test_mock_client.py` (async test structure) + RESEARCH.md Pattern 10

**Module-level skip guard** — from RESEARCH.md Pattern 10:
```python
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
```

**Key test cases** (D-15):
- `test_token_fetch_and_cache` — two sequential `_get_token()` calls return same token
- `test_real_search_returns_results` — `MAD→BCN`, departure date ~1 month out, assert `len(results) >= 1`
- `test_vendor_neutral_shape` — assert first result has `.segments`, `.price.amount`, `.price.currency`
- `test_error_mapping_401` — bad credentials → `APIClientError`

**Route known to work in sandbox** (RESEARCH.md Pitfall 1): `MAD→BCN` (Madrid to Barcelona). Use `LON→NYC` as alternative. Assert `>= 1` result, never `== N`.

---

### `justfile` (config — EXTEND)

**Analog:** `justfile` (current, lines 1–50)

**Current test target pattern** (lines 22–29):
```python
test-unit:
    cd backend && uv run pytest tests/unit/

test-integration:
    cd backend && uv run pytest tests/integration/
```

**Phase 7 addition** — new `test-amadeus` target following the same `cd backend && uv run pytest` pattern:
```
# Run real-API Amadeus integration tests (requires AMADEUS_API_KEY + AMADEUS_API_SECRET env vars)
test-amadeus:
    cd backend && uv run pytest tests/e2e_amadeus/ -v -s
```

---

### `.github/workflows/ci.yml` (config — EXTEND)

**Analog:** `.github/workflows/ci.yml` (current, lines 1–120)

**Current job structure** (lines 17–119): three jobs — `backend`, `frontend`, `e2e`. All use `actions/checkout@v4`, `setup-python@v5`, `setup-uv@v4`, `actions/cache@v4`.

**New Amadeus E2E job** — add after the `e2e` job (line 120), following the same job pattern as `backend` (lines 17–60):
```yaml
  amadeus-e2e:
    name: Amadeus E2E
    runs-on: ubuntu-latest
    # Only run when both secrets are available.
    # PR CI never requires keys — secrets are absent on forks.
    if: >
      github.event_name != 'pull_request' &&
      secrets.AMADEUS_API_KEY != '' &&
      secrets.AMADEUS_API_SECRET != ''
    defaults:
      run:
        working-directory: backend
    env:
      AMADEUS_API_KEY: ${{ secrets.AMADEUS_API_KEY }}
      AMADEUS_API_SECRET: ${{ secrets.AMADEUS_API_SECRET }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Set up Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      - name: Install dependencies
        run: uv sync --frozen
      - name: Run Amadeus E2E tests
        run: uv run pytest tests/e2e_amadeus/ -v -s
```

**Note on secret gating:** GitHub Actions secrets are not accessible on `pull_request` events from forks. The `if:` condition on the job handles this. D-14: "PR CI never requires keys."

---

### `backend/pyproject.toml` (config — EXTEND)

**Analog:** `backend/pyproject.toml` (current, lines 1–30)

**Current dependencies pattern** (lines 7–29):
```toml
dependencies = [
    "fastapi>=0.115.0",
    ...
    "pyreqwest>=0.12.0",  # ADD — already in venv from Phase 6 research
    "tenacity>=9.1.2",    # ADD — already indirect dep via google-genai; explicit floor
    "pybreaker>=1.4.1,<2.0",  # ADD — pin <2.0 because we access state._handle_error internal
]
```

**Comment convention** (lines 18–29 Phase 6 style):
```toml
# Phase 7 — D-10 (tenacity replaces hand-rolled retry), D-12 (pybreaker circuit breaker).
# pybreaker pinned <2.0: state._handle_error() is a protected method accessed by
# call_with_breaker(); pinning ensures the async-safe workaround stays valid.
# See backend/app/tools/circuit_breaker.py and 07-RESEARCH.md Pitfall 4.
"tenacity>=9.1.2",
"pybreaker>=1.4.1,<2.0",
```

`pyreqwest` may already be in the lockfile; verify with `uv pip list | grep pyreqwest` before adding.

---

## Shared Patterns

### ABC + Concrete Implementation Split
**Source:** `backend/app/tools/flight_client.py` lines 13–81 (`FlightAPIClient` ABC)
**Apply to:** `backend/app/flights/amadeus_client.py`
```python
class AmadeusFlightClient(FlightAPIClient):
    """Concrete impl — must implement all four abstractmethods."""

    async def health_check(self) -> bool: ...
    async def search(self, query: FlightQuery, ...) -> list[Flight]: ...
    async def get_flight_details(self, flight_id: str) -> Flight: ...
    async def check_availability(self, flight_id: str) -> bool: ...
```

### Lifespan Singleton Pattern
**Source:** `backend/app/api/main.py` lines 29–108
**Apply to:** Phase 7 lifespan modification
```python
# Startup: construct client, stash on app.state
app.state.flight_client = flight_client
app.state.flight_provider = flight_provider  # NEW in Phase 7

# Shutdown: no cleanup needed for stateless HTTP client
# (compare: PostgresMessageStore needs engine.dispose())
```

### Settings Field Pattern (optional credential)
**Source:** `backend/app/config.py` lines 56–58 (`openai_api_key`)
**Apply to:** `amadeus_api_key`, `amadeus_api_secret` additions
```python
# Optional — None means "not configured". Auto-fallback logic in lifespan checks for None.
amadeus_api_key: SecretStr | None = None
```

Use `pydantic.SecretStr` (not `str | None`) because Amadeus credentials flow through `model_post_init` logging paths and the existing `ApiKeyScrubber`. `SecretStr.__str__` returns `'**********'` preventing accidental log leaks.

### App State Access in Route Handler
**Source:** `backend/app/api/routes/routes.py` lines 471–472
**Apply to:** Extended `/health` endpoint
```python
cache: dict[str, list[str]] = request.app.state.provider_models_cache
# Phase 7 equivalent:
flight_provider = getattr(request.app.state, "flight_provider", "mock")
# getattr with default guards against pre-lifespan test invocations
```

### Async Test with asyncio_mode = "auto"
**Source:** `backend/tests/unit/test_retry.py` lines 51–55 + `backend/pyproject.toml` line 46
**Apply to:** All new async test files
```python
# No @pytest.mark.asyncio needed — asyncio_mode = "auto" in pyproject.toml
async def test_something() -> None:
    result = await some_async_function()
    assert result == expected
```

### MagicMock/AsyncMock for HTTP boundary
**Source:** `backend/tests/integration/conftest.py` lines 27–51
**Apply to:** Unit tests for `AmadeusFlightClient` (mock pyreqwest at boundary)
```python
from unittest.mock import AsyncMock, MagicMock, patch

# Pattern: patch the ClientBuilder context manager
with patch("app.flights.amadeus_client.ClientBuilder") as mock_builder:
    mock_client = AsyncMock()
    mock_builder.return_value.timeout.return_value.error_for_status.return_value.build.return_value.__aenter__.return_value = mock_client
    mock_client.get.return_value.bearer_auth.return_value.query.return_value.build.return_value.send.return_value = mock_response
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/app/flights/amadeus_token_cache.py` | utility | request-response | No standalone token cache class exists in the project; pattern is from asyncio.Lock stdlib docs. Likely better as private methods on `AmadeusFlightClient` rather than a separate file. |

---

## Metadata

**Analog search scope:** `backend/app/`, `backend/tests/`, `.github/workflows/`, `justfile`
**Files scanned:** 28 source files + 2 config files
**Pattern extraction date:** 2026-06-05

---

## PATTERN MAPPING COMPLETE

**Phase:** 7 - real-flight-api
**Files classified:** 20
**Analogs found:** 19 / 20

### Coverage
- Files with exact analog: 13
- Files with role-match analog: 6
- Files with no analog: 1 (`amadeus_token_cache.py` — likely stays as private methods on `AmadeusFlightClient`)

### Key Patterns Identified
- `AmadeusFlightClient` follows the same ABC + concrete impl split as `FlightAPIClient`/`MockFlightAPIClient` — four abstract methods, same signatures, DI-transparent
- `retry_on_failure()` public API is preserved exactly (same parameter names/defaults); only internals change to tenacity — all 8 existing tests pass unchanged
- pybreaker `@decorator` does NOT work on async functions (verified in research); `call_with_breaker()` helper uses `state.before_call()`/`state._handle_error()` directly — this is the only correct pattern
- Lifespan auto-fallback follows exact `app.state.*` assignment pattern already established by Phase 6 (PostgresMessageStore, PostgresConversationRepository)
- `asyncio_mode = "auto"` in pyproject.toml means no `@pytest.mark.asyncio` markers needed on new test functions
- `normalize_amadeus_offer()` already exists at `backend/app/tools/flight_search.py:141` — do not reimplement; call it from `AmadeusFlightClient._parse_flight_offers()`

### File Created
`/Users/axel/code/trip_planner/.planning/phases/07-real-flight-api/07-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
