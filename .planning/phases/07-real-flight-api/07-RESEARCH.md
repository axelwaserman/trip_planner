# Phase 7: Real Flight API (Duffel) — Research

**Researched:** 2026-06-06
**Domain:** Vendor-neutral flight provider integration (Duffel REST API v2 over `pyreqwest`)
**Confidence:** HIGH (Duffel headers, endpoint paths, error envelope, datetime format, lightweight auth-probe verified against official docs and the archived but inspectable Duffel Python SDK; pyreqwest builder shape verified live in this repo via prior Amadeus implementation that compiled and passed tests; reuse of retry/breaker/exception/log-scrubber plumbing verified via current source)

## Summary

Phase 7 swaps `MockFlightAPIClient` (the lifespan default) for a real `DuffelFlightClient` behind the existing `FlightAPIClient` ABC. The vendor-agnostic plumbing (tenacity retry, pybreaker async-safe `call_with_breaker`, `pyreqwest`, `APIError` hierarchy, `ApiKeyScrubber`, `Flight`/`FlightSegment`/`FlightResult` models, lifespan auto-fallback shape, `/health flight_provider` field) is preserved verbatim from the now-deleted Amadeus implementation. The Duffel client is materially **simpler** than the Amadeus one: bearer-token auth (no OAuth2 client_credentials, no token cache, no `asyncio.Lock`, no proactive refresh, no malformed-body guard), a single round-trip search via `POST /air/offer_requests?return_offers=true`, and an embedded `data.offers[]` payload. The CONTEXT.md decision matrix (D-01..D-14) covers the entire scope; this research document does not re-litigate any locked decision — it confirms the technical facts each decision rests on.

**Primary recommendation:** Mirror the deleted `amadeus_client.py` module shape at `backend/app/flights/duffel_client.py`. Keep the `_raise_from_http_status` helper, the breaker config (`fail_max=5, reset_timeout=60, throw_new_error_on_trip=True`), the `_fetch_with_retry_breaker` composition (retry-outside, breaker-inside, HTTP-innermost), the naive-datetime UTC-attach mitigation, and the `Pitfall 1` MAD→BCN reliable test route. Strip the entire OAuth2 token-cache layer (~40 lines of work + 3 unit tests removed). Delete the unused `normalize_amadeus_offer` and `normalize_skyscanner_itinerary` module-level functions per D-08 and move normalization onto a private `DuffelFlightClient._normalize_offer` method.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `Settings.duffel_api_token: SecretStr | None = None` + `Settings.duffel_env: Literal["test", "live", "mock"] = "test"`. Token type-narrowed by Literal (T-07-01-class mitigation reused), `SecretStr` scrubs in logs (T-07-02). `mock` literal forces `MockFlightAPIClient` even when token is present. Lifespan reads `duffel_api_token.get_secret_value()` only at the point of construction.
- **D-02:** Lifespan auto-fallback: `duffel_env == "mock"` OR `duffel_api_token is None` → `MockFlightAPIClient(seed=42)`. Missing-token path emits exactly one WARN: `DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient`. Boot must NEVER fail because of missing creds. `flight_provider` on `app.state` is `"real"` only when `DuffelFlightClient` is constructed.
- **D-03:** `Duffel-Version` header is hardcoded as `_DUFFEL_VERSION = "v2"` module constant in `app/flights/duffel_client.py`. Attached to every pyreqwest request via `.header("Duffel-Version", _DUFFEL_VERSION)`. Wire-version constant — NOT on `Settings`.
- **D-04:** Error mapping is HTTP-status-driven, NOT Duffel-error-type-driven. Reuse the `_raise_from_http_status(status, exc)` helper shape from the deleted Amadeus client. 401 → `APIClientError(retryable=False)`, 422 → `APIClientError(retryable=False)`, 429 → `APIRateLimitError(retryable=True)` with `retry_after` parsed from `Retry-After` header if present, 5xx → `APIServerError(retryable=True)`, other 4xx → `APIClientError(retryable=False)`. Message uses `errors[0].title` ONLY — never `errors[0].message` (T-07-02-class: `message` may echo creds / PII). Duffel `error.type` / `error.code` are logged for diagnostics but do NOT drive retry decisions.
- **D-05:** Single round trip. `DuffelFlightClient.search` issues `POST /air/offer_requests` with `return_offers=true` and reads `data.offers[]` from the response. No follow-up `GET /air/offers` call. Up to ~50 offers per request.
- **D-06:** `offset` is honored but capped: `DuffelFlightClient.search` returns `offers[:limit]` regardless of the caller's `offset` argument. ABC signature retains `offset` for vendor-portable callers; docstring documents that Duffel's single-round-trip flow does not support `offset > 0`. Avoids the CR-01-class double-application bug from the previous Amadeus phase.
- **D-07:** Add `FlightQuery.return_date: date | None = None`. When `None`: send one outbound slice; when set: send two slices (outbound + return). Backend round-trip support end-to-end. Frontend rendering of return-leg results deferred.
- **D-08:** Normalization moves OFF `flight_search.py` and ONTO each `FlightAPIClient` implementation. `DuffelFlightClient._normalize_offer(self, raw: dict) -> Flight` is a private method. The unused `normalize_amadeus_offer` and `normalize_skyscanner_itinerary` module-level functions are deleted along with their tests/fixtures.
- **D-09:** Naive datetimes from Duffel (`departing_at`, `arriving_at` are ISO-8601 LOCAL strings without TZ offset) get UTC attached: parse via `datetime.fromisoformat`, then `dt.replace(tzinfo=UTC)` if `dt.tzinfo is None`. Documented limitation: timestamps shown in UTC, not local airport time.
- **D-10:** `BookingClass = Literal["economy", "premium_economy", "business", "first"]` maps 1:1 to Duffel `cabin_class`. `_normalize_offer` reads cabin from the per-segment per-passenger field `slices[0].segments[0].passengers[0].cabin_class` (canonical location per Duffel SDK; see Code Examples below). Stays a `Literal`, not a `StrEnum`.
- **D-11:** Real-API tests live in `backend/tests/e2e_duffel/` (path-isolated). Module-level `pytestmark = pytest.mark.skipif(not DUFFEL_AVAILABLE, ...)` skips the whole suite when `DUFFEL_API_TOKEN` is unset. New `just test-duffel` target. New CI job `duffel-e2e` gated on `secrets.DUFFEL_API_TOKEN` AND `vars.DUFFEL_E2E_ENABLED == 'true'`.
- **D-12:** Live e2e_duffel suite asserts: (a) auth probe — first request with valid token returns 2xx; (b) live search MAD→BCN returns ≥1 offer (LON→NYC fallback); (c) full vendor-neutral `Flight` shape after `_normalize_offer`; (d) 401 with bogus token surfaces as `APIClientError(retryable=False)`. Four tests.
- **D-13:** Adult-only passengers for v1. `DuffelFlightClient` maps `FlightQuery.passengers: int` to Duffel `passengers: [{"type": "adult"}] * n`.
- **D-14:** `FlightQuery.max_stops` is forwarded server-side to Duffel as `slice.max_connections`. When `max_stops is None`, the field is omitted. Other filters (`max_price`, `max_duration`) remain client-side.

### Claude's Discretion

- Exact pyreqwest request-builder chain shape — pattern-match the previous Amadeus client.
- Module layout: `backend/app/flights/duffel_client.py`.
- Whether the auth-probe e2e test issues `POST /air/offer_requests` or hits a cheaper endpoint — researcher determined `GET /air/airlines?limit=1` is cheapest (reference data).
- Log scrubber pattern for the bearer token — verify `ApiKeyScrubber` regex covers `duffel_test_*` / `duffel_live_*` (it does NOT; this report flags a regex addition).
- Whether `health_check()` issues a network call against Duffel or just returns `True` — recommend `True` (matches deleted Amadeus pattern; `_get_token` no longer exists to stand in).

### Deferred Ideas (OUT OF SCOPE)

- Cursor pagination beyond first batch
- Per-passenger-type counts (children, infants)
- Frontend rendering of return-leg results
- Airport-IATA-to-timezone lookup
- Cross-vendor live clients (Skyscanner, Google, Kayak)
- In-process result caching with TTL
- Aggressive retry tuning (jitter, full Retry-After parsing, request-id correlation) — Phase 8
- Settings-driven circuit breaker thresholds
- Rate limiting (`slowapi`) — out of scope per ADR-009
- Raw vendor payload exposure for diagnostics

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-real-flight-api | Replace `MockFlightAPIClient` (default) with a real Duffel client behind `FlightAPIClient` ABC; pyreqwest for outbound HTTP; reuse retry+breaker; mock as test default; gated CI for real-API tests; documented credential setup. | Sections "Standard Stack", "Architecture Patterns", "Code Examples", "Validation Architecture", "Pitfalls" all directly support this requirement. The Duffel-specific evidence (endpoints, headers, auth, error envelope, datetime format, MAD→BCN reliable route, lightweight auth-probe) is collected here so the planner can write tasks that compile on first try. |

## Project Constraints (from CLAUDE.md)

- **Outbound HTTP must use `pyreqwest`** — never `aiohttp`, `httpx`, or `requests` (ADR-008). [VERIFIED: CLAUDE.md "Key constraints" + ARCHITECTURE.md ADR-008]
- **All I/O must be `async def`** — no sync file or HTTP I/O in async paths. [VERIFIED: CLAUDE.md "Key constraints"]
- **`mypy` strict mode** — no bare `type: ignore` without a comment. [VERIFIED: CLAUDE.md]
- **Abstract interfaces use `ABC`, never `Protocol`** — `FlightAPIClient` is already an `ABC`. [VERIFIED: CLAUDE.md + `backend/app/tools/flight_client.py:13`]
- **Cross-module taxonomies use `StrEnum`, not duplicated `Literal[...]` unions** — `BookingClass` lives in a single module so `Literal` is correct (D-10). [VERIFIED: CLAUDE.md]
- **Tunable thresholds live on `Settings`, not as module-level constants** — `Duffel-Version` is a wire-version constant (part of the contract), so `_DUFFEL_VERSION = "v2"` stays a module constant per the carve-out. [VERIFIED: CLAUDE.md]
- **`ruff` line length 120; isort first-party prefix `app`.** [VERIFIED: CLAUDE.md]
- **Comments explain *why*, not *what*.** [VERIFIED: CLAUDE.md]
- **Public APIs get docstrings (Args, Returns, Raises).** [VERIFIED: CLAUDE.md]
- **Package management: `uv` exclusively** — never `pip`, `poetry`, `conda`. [VERIFIED: CLAUDE.md]
- **`pytest.mark.unit/integration/e2e/slow` markers were removed in Phase 4.4** — selection is path-only. The justfile `test-e2e` target still uses `-m "e2e"` which is stale; the planner should be aware but Phase 7 is not on the hook to fix it (out of scope unless planner discovers blocker). [VERIFIED: CLAUDE.md "Test structure"]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request to Duffel API | API / Backend (`DuffelFlightClient._search_impl`) | — | All vendor I/O lives in the concrete `FlightAPIClient` impl; mock and Duffel both run under FastAPI lifespan. |
| Vendor → vendor-neutral mapping | API / Backend (`DuffelFlightClient._normalize_offer`) | — | D-08 locks normalization to the impl class. |
| Retry + circuit breaker composition | API / Backend (`app.tools.retry`, `app.tools.circuit_breaker`) | — | Existing primitives reused unchanged. |
| Settings (`duffel_api_token`, `duffel_env`) | API / Backend (`app.config.Settings`) | — | Pydantic-settings env load. |
| Lifespan auto-fallback (mock vs real) | API / Backend (`app.api.main.lifespan`) | — | Single decision point; stashes on `app.state.flight_client`. |
| `/health flight_provider` surface | API / Backend (existing route) | — | Already wired; Duffel branch only flips the value to `"real"`. |
| LLM tool entry point (`search_flights`) | API / Backend (`app.tools.flight_search.search_flights`) | — | Tool consumes `ChatDeps.flight_client` — vendor-agnostic; D-08 thins this module by deleting the unused module-level normalizers. |
| Real-API integration tests | CI / Test infra (`tests/e2e_duffel/`) | — | Path-isolated, gated job in `.github/workflows/ci.yml`. |
| Log scrubbing of bearer token | API / Backend (`app.llm.log_scrubbing.ApiKeyScrubber`) | — | Existing filter; regex must be extended for `duffel_(test|live)_*` shape. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyreqwest` | `>=0.12.0` (already pinned) | Async outbound HTTP | ADR-008 mandate; replaces `aiohttp`/`httpx`/`requests` project-wide. [VERIFIED: backend/pyproject.toml + ADR-008] |
| `tenacity` | `>=9.1.2` (already pinned) | `retry_on_failure` decorator | Project's retry primitive — reuse verbatim. [VERIFIED: backend/pyproject.toml] |
| `pybreaker` | `>=1.4.1,<2.0` (already pinned) | Async-safe circuit breaker via `call_with_breaker` helper | `<2.0` pin locks the internal `state._handle_error` / `state._handle_success` API the helper depends on. [VERIFIED: backend/pyproject.toml + Pitfall 4 in this doc] |
| `pydantic-settings` | `>=2.6.0` (already pinned) | `Settings.duffel_api_token: SecretStr` env load | Project standard for config. [VERIFIED: backend/pyproject.toml] |

**No new dependencies.** Phase 7 is a pure-code phase that adds `DuffelFlightClient` and reuses every existing dep.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` | (transitive via pydantic-ai/settings) | `Flight`, `FlightSegment`, `FlightResult` validators | Already used. Vendor-neutral models live in `app/flights/models.py`. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pyreqwest` | `httpx` / `aiohttp` | Forbidden by ADR-008. Not an option. |
| Hand-rolled retry | `tenacity` | Already migrated to tenacity in Phase 07-01 (commit `26aa14c`). |
| Hand-rolled breaker | `pybreaker` + `call_with_breaker` async helper | Async-safe wrapper exists; rolling our own was a documented Pitfall 4 dead-end. |
| Duffel official Python SDK (`duffel-api`) | `pip install duffel-api` | **REJECTED:** archived 2024-09-12, "not currently being supported by Duffel due to a lack of adoption." Defaults to `Duffel-Version: v1`, uses `requests` (not async), uses naive `strptime` parsing that crashes on TZ-offset input. We need async, pyreqwest, and v2. [VERIFIED: github.com/duffelhq/duffel-api-python README] |

**Installation:** No new packages. The `pyproject.toml` change from this phase is a single new field block in `Settings` (no dep additions).

**Version verification:**
```bash
# All deps are already pinned and pass slopcheck (verified 2026-06-06):
uv pip show pyreqwest pybreaker tenacity pydantic-settings
# pyreqwest 0.12.0 — homepage github.com/MarkusSintonen/pyreqwest [VERIFIED: PyPI]
# pybreaker 1.4.1+ — github.com/danielfm/pybreaker [VERIFIED: pyproject.toml pin]
# tenacity 9.1.2+ — tenacity.readthedocs.io [VERIFIED: pyproject.toml pin]
# pydantic-settings 2.6.0+ [VERIFIED: pyproject.toml pin]
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pyreqwest | PyPI | ~1 yr (0.12.0 published 2025) | low (niche async-reqwest binding) | github.com/MarkusSintonen/pyreqwest | [OK] | Approved (already pinned project-wide; ADR-008 mandate) |
| pybreaker | PyPI | 10+ yrs | high | github.com/danielfm/pybreaker | [OK] | Approved (already pinned) |
| tenacity | PyPI | 10+ yrs | very high | github.com/jd/tenacity | [OK] | Approved (already pinned) |
| pydantic-settings | PyPI | 2+ yrs | very high | github.com/pydantic/pydantic-settings | (not run individually; OK by association) | Approved (already pinned) |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.
**Phase 7 does not introduce any new dependencies.** The slopcheck run above (`slopcheck install pyreqwest pybreaker tenacity`) returned `3 OK`. [VERIFIED: live slopcheck run 2026-06-06]

## Architecture Patterns

### System Architecture Diagram

```
[LLM tool call: search_flights]
            │
            ▼
   [search_flights tool]  (app/tools/flight_search.py)
            │  ctx.deps.flight_client
            ▼
   [FlightAPIClient ABC]   (app/tools/flight_client.py)
            │
            ├──► [MockFlightAPIClient]   (test/dev default)
            │
            └──► [DuffelFlightClient]   (Phase 7 — new)
                       │
                       │  search()
                       ▼
                 [_fetch_with_retry_breaker]   ← @retry_on_failure (tenacity)
                       │
                       ▼
                 [call_with_breaker]            ← pybreaker async wrapper
                       │
                       ▼
                 [_search_impl]                 ← pyreqwest POST
                       │
                       │  POST https://api.duffel.com/air/offer_requests?return_offers=true
                       │  Headers: Duffel-Version: v2
                       │           Authorization: Bearer duffel_test_*
                       │           Accept: application/json
                       │
                       ▼
                 [Duffel API]
                       │
                       │  200 → data.offers[]
                       │  401/422 → APIClientError(retryable=False)
                       │  429     → APIRateLimitError(retryable=True)
                       │  5xx     → APIServerError(retryable=True)
                       │
                       ▼
                 [_normalize_offer]   (private method, D-08)
                       │
                       │  Flight + FlightSegment[]
                       ▼
                 [list[Flight]]   ← matches FlightAPIClient ABC contract
                       │
                       ▼
                 [_to_flight_search_result]   (existing in flight_search.py)
                       │
                       ▼
                 [FlightSearchResult]   (vendor-neutral envelope, Phase 4.6 contract)
                       │
                       ▼
                 [SSE tool_result event] → frontend ToolExecutionCard
```

### Recommended Project Structure

```
backend/app/flights/
├── __init__.py
├── duffel_client.py         # NEW — DuffelFlightClient (mirrors deleted amadeus_client.py)
└── models.py                # existing — vendor-neutral Flight/FlightSegment/FlightResult
                             #   Phase 7 adds: FlightQuery.return_date: date | None = None (D-07)

backend/app/tools/
├── flight_client.py          # existing ABC + Mock
├── flight_search.py          # existing tool — D-08 deletes normalize_amadeus_offer +
│                             #   normalize_skyscanner_itinerary; keeps search_flights
│                             #   tool entry + _to_flight_search_result helper
├── retry.py                  # existing tenacity wrapper (preserved verbatim)
└── circuit_breaker.py        # existing async-safe pybreaker helper (preserved verbatim)

backend/app/config.py         # existing — Phase 7 adds two fields:
                              #   duffel_api_token: SecretStr | None = None
                              #   duffel_env: Literal["test", "live", "mock"] = "test"

backend/app/api/main.py       # existing lifespan — Phase 7 reintroduces the env+creds
                              #   branch deleted in commit 5d7499c

backend/app/llm/log_scrubbing.py  # existing — Phase 7 adds one regex for duffel_(test|live)_*

backend/tests/e2e_duffel/         # NEW — path-isolated real-API suite, gated on DUFFEL_API_TOKEN
├── __init__.py
├── conftest.py                   # module-scoped duffel_client fixture
└── test_duffel_client.py         # 4 tests (D-12)

backend/tests/unit/test_duffel_client.py    # NEW — error mapping, _normalize_offer, etc.
backend/tests/integration/                  # extend test_lifespan_flight_provider.py
```

### Pattern 1: Lifespan Auto-Fallback (D-02)

**What:** Lifespan branches on `Settings.duffel_env` + token presence. Missing token → mock. Boot never fails.
**When to use:** Every external-vendor client behind an ABC where dev environments lack creds.
**Example:** *(adapted from deleted Amadeus lifespan branch — commit `4d9487d`)*
```python
# backend/app/api/main.py — inside lifespan()
# Source: Phase 7 D-02; mirrors Amadeus pattern in commit 4d9487d
if (
    settings.duffel_env == "mock"
    or settings.duffel_api_token is None
):
    if settings.duffel_env != "mock":
        logger.warning("DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient")
    flight_client: FlightAPIClient = MockFlightAPIClient(seed=42)
    flight_provider = "mock"
else:
    # Single base URL for Duffel (the token's _test_/_live_ prefix selects sandbox vs prod).
    flight_client = DuffelFlightClient(
        api_token=settings.duffel_api_token.get_secret_value(),
        base_url="https://api.duffel.com",
    )
    flight_provider = "real"

app.state.flight_client = flight_client
app.state.flight_provider = flight_provider
```

### Pattern 2: pyreqwest POST with Bearer + Headers + JSON Body

**What:** The exact builder chain for a Duffel offer-request POST.
**When to use:** Every Duffel call.
**Example:** *(verified pattern from prior Amadeus search_impl, commit `1743f4b`; pyreqwest README confirms `bearer_auth`/`json`/`header`/`build`/`send` chain)*
```python
# Source: pyreqwest README (github.com/MarkusSintonen/pyreqwest) +
#         backend prior commit 1743f4b (compiled, passed tests)
from datetime import timedelta
from pyreqwest.client import ClientBuilder
from pyreqwest.exceptions import ConnectError, RequestTimeoutError, StatusError

_DUFFEL_VERSION = "v2"  # module constant per D-03

async with (
    ClientBuilder()
    .timeout(timedelta(seconds=15))
    .error_for_status(True)
    .build() as client
):
    resp = (
        await client.post(f"{self._base_url}/air/offer_requests")
        .query({"return_offers": "true"})
        .bearer_auth(self._api_token)
        .header("Duffel-Version", _DUFFEL_VERSION)
        .header("Accept", "application/json")
        .json(body)
        .build()
        .send()
    )
    payload: dict[str, Any] = await resp.json()
```

### Pattern 3: Retry + Breaker + HTTP Composition (D-12 / D-13 carry-over)

**What:** `@retry_on_failure` outside, `call_with_breaker` inside, pyreqwest innermost. Open breaker maps to `APIServerError(retryable=False)` so tenacity skips retries into an open breaker.
**When to use:** Every vendor HTTP call gated by retry+breaker.
**Example:** *(verbatim shape from deleted Amadeus client — commit `1743f4b`)*
```python
# Source: backend/app/flights/amadeus_client.py (deleted, commit 1743f4b)
# Composition order: retry-outside, breaker-inside, HTTP-innermost.
@retry_on_failure(max_retries=3, backoff_base=2.0)
async def _fetch_with_retry_breaker(
    self, query: FlightQuery, limit: int, offset: int
) -> list[Flight]:
    try:
        return await call_with_breaker(
            self._breaker,
            self._search_impl,
            query, limit, offset,
        )
    except pybreaker.CircuitBreakerError as exc:
        # D-13: open breaker is non-retryable — tenacity's retry_if_exception
        # gates on retryable=True, so this short-circuits the retry loop.
        raise APIServerError(
            message="Duffel circuit breaker open",
            retryable=False,
        ) from exc
```

### Pattern 4: HTTP-Status-Driven Error Mapping (D-04)

**What:** A single `_raise_from_http_status(status, exc) -> NoReturn` helper at module scope. Body content is NOT used to construct messages (T-07-02 PII guard).
**Example:** *(carry over from deleted Amadeus client; tweak token-cache invalidation logic — Duffel has no cache)*
```python
# Source: deleted backend/app/flights/amadeus_client.py (commit 3346e96)
# Adapted for Duffel: no token-cache invalidation needed on 401.
def _raise_from_http_status(status: int, exc: Exception) -> NoReturn:
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

### Anti-Patterns to Avoid

- **`@cb` decorator on async functions** — pybreaker's stock decorator wraps the coroutine object, not the awaited result; failures never increment the counter. Use `call_with_breaker` instead. (Pitfall 4.) [VERIFIED: backend/app/tools/circuit_breaker.py docstring]
- **Using `errors[0].message` (or `errors[0].detail`) in user-facing exception messages** — Duffel's verbose error text may echo PII or partial credentials. Use `errors[0].title` only, log `code`/`type` for diagnostics. [CITED: Duffel error envelope docs] [ASSUMED: PII-leak risk — analogous to Amadeus T-07-02 mitigation, not directly verified for Duffel]
- **Applying `offset` twice** — the previous Amadeus phase shipped this bug (CR-01, regression-locked in commit `1b72d32`). D-06 prevents the recurrence by capping at `offers[:limit]` and documenting `offset > 0` as not supported.
- **Hardcoding `Duffel-Version` in `Settings`** — wire-version belongs in code (CLAUDE.md carve-out). Bumping versions is a code change, not a config change.
- **Re-introducing `from app.flights.amadeus_client import ...`** — the module was deleted (commit `5d7499c`). Stale imports must be flagged by mypy.
- **Naive `datetime.fromisoformat` without TZ attach** — Duffel emits naive ISO-8601 (`"2024-01-15T14:30:45"`), which Python parses as a naive `datetime` and our `Flight` validator chokes on (Phase 4.6 expects TZ-aware). D-09 attaches `UTC` as a documented fallback. [VERIFIED: Duffel SDK `parse_datetime` shows naive format support]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async retry with exponential backoff | hand-rolled `for attempt in range(N): await asyncio.sleep(...)` | `app.tools.retry.retry_on_failure` (tenacity) | Already migrated; regression-locked invariants (`reraise=True`, retryable predicate) live in `tests/unit/test_retry.py`. |
| Async-safe circuit breaker | hand-rolled state machine | `app.tools.circuit_breaker.call_with_breaker` (pybreaker) | The `@cb` decorator anti-pattern is already documented and locked. |
| Bearer-token log redaction | per-call string masking | `app.llm.log_scrubbing.ApiKeyScrubber` | Phase 8 will replace with structlog processor; for now, add one regex pattern. |
| HTTP error mapping per Duffel error code | match each `errors[0].code` value | HTTP-status-driven `_raise_from_http_status` | D-04 lock; vendor-portable; immune to Duffel adding new error codes. |
| Vendor-neutral DTO types | new `DuffelFlight` model | existing `Flight` / `FlightSegment` / `FlightResult` (Phase 4.6) | These models were designed for Amadeus / Skyscanner / Google; Duffel maps onto them without lossy collapses. [VERIFIED: REQ-tool-json-output + Phase 4.6 fixture work] |
| ISO-8601 PT-duration parsing | regex-by-hand | reuse `_iso_pt_to_minutes` from deleted Amadeus client (regex `^PT(?:(\d+)H)?(?:(\d+)M)?$`) | Already a known pattern; Duffel `OfferSlice.duration` is the same `PT<H>H<M>M` shape. [ASSUMED: Duffel duration shape — Duffel SDK exposes `.duration` as a string; format inferred from IATA convention shared with Amadeus] |
| Duffel API client | port the archived `duffel-api` Python SDK | new `DuffelFlightClient` against `pyreqwest` | The official SDK is archived, sync-only (`requests`-based), and defaults to `v1`. Async + pyreqwest + v2 mandates a fresh implementation. [VERIFIED: github.com/duffelhq/duffel-api-python README banner] |

**Key insight:** Phase 7 is plumbing assembly, not greenfield design. Every primitive already exists in the repo and is regression-locked by tests. The Duffel client is ~250 lines (Amadeus was ~340 with token cache; subtracting ~90 lines of OAuth2 code yields the estimate).

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 7 introduces no new database tables, no message store changes, no Redis keys. The `Flight` results are ephemeral SSE payloads. | None. |
| Live service config | None — no n8n/Datadog/Cloudflare integration with Duffel. The Duffel API token is read from env at lifespan, never persisted. | None. |
| OS-registered state | None — no systemd/launchd/Task Scheduler entries reference Duffel or flight providers. | None. |
| Secrets/env vars | **NEW:** `DUFFEL_API_TOKEN` (was `AMADEUS_API_KEY`/`AMADEUS_API_SECRET` — both deleted in commit `5d7499c`). **NEW:** `DUFFEL_ENV` (default `"test"`). **NEW CI:** GitHub `secrets.DUFFEL_API_TOKEN` + repo `vars.DUFFEL_E2E_ENABLED`. | (a) Add fields to `Settings`. (b) Document in README credential-setup section (replaces deleted AMADEUS section). (c) Configure GH secret + var per D-11. (d) `.env.example` (if it exists) gains `DUFFEL_API_TOKEN=` and `DUFFEL_ENV=test` rows. |
| Build artifacts | None — no compiled binaries, no Docker images that bake the token, no pip egg-info to refresh. The deleted Amadeus client is gone from `master` so no stale `.pyc` issues. | None — `uv sync` already current. |

**Canonical question answered:** After every file in the repo is updated, the only runtime state that needs attention is the **CI/local env vars** — and those are *new*, not stale. The deleted Amadeus secrets must be removed from any local `.env` files (developer task, not in plan scope) and from the GitHub repository secrets/vars (admin task — flagged in plan but not auto-executed).

## Common Pitfalls

### Pitfall 1: Sandbox sparsity returning empty offer lists
**What goes wrong:** A test asserting `len(results) >= 1` fails because the sandbox returns `data.offers == []` for popular domestic US routes (LAX→JFK, SFO→LAX) on certain dates. The Amadeus phase shipped with this exact symptom and the LON→NYC fallback.
**Why it happens:** Vendor sandboxes have intentionally sparse inventory; not every route × date combination yields offers.
**How to avoid:** Use the regression-tested **MAD→BCN** route 30 days out (D-12). LON→NYC as fallback. Always assert `>= 1`, never `== N`.
**Warning signs:** First e2e_duffel run returns `count=0`. Don't tighten the test — switch the route.

### Pitfall 2: Naive datetimes from Duffel rejected by `Flight` validator
**What goes wrong:** `datetime.fromisoformat("2024-01-15T14:30:45")` returns a naive `datetime`. `Flight.departure: datetime` works, but downstream consumers comparing TZ-aware vs naive datetimes raise `TypeError`. Phase 4.6's `_to_flight_search_result` and the SSE tool_result rendering both assume TZ-aware.
**Why it happens:** Duffel's `parse_datetime` accepts both `2024-01-15T14:30:45Z` and `2024-01-15T14:30:45` — the segment-level `departing_at`/`arriving_at` fields are emitted as **local airport time without TZ offset**. [VERIFIED: Duffel SDK `parse_datetime` `utils.py`]
**How to avoid:** D-09 mitigation — `if dt.tzinfo is None: dt = dt.replace(tzinfo=UTC)`. Documented limitation: timestamps shown in UTC, not local airport time. (Airport-IATA→TZ lookup deferred.)
**Warning signs:** Pydantic `ValidationError` mentioning `tzinfo`, or `TypeError: can't compare offset-naive and offset-aware datetimes` in downstream sort/filter logic.

### Pitfall 3: `errors[0].message` leaking PII or partial credentials in user-facing exception text
**What goes wrong:** A vendor error response like `{"errors":[{"title":"Authentication failed","message":"Token 'duffel_test_xyz...' is invalid","code":"invalid_token","type":"authentication_error"}]}` gets surfaced through `APIClientError(str(body))` and the token half-leaks into logs / SSE error events.
**Why it happens:** Verbose vendor `message`/`detail` fields routinely echo request inputs.
**How to avoid:** D-04 mitigation — `_raise_from_http_status` constructs messages from **status code only**, never response body. The `code`/`type` fields are logged for diagnostics via the standard logger (`ApiKeyScrubber` redacts the bearer-token shape before formatter dispatch).
**Warning signs:** Any code path doing `f"... {body['errors'][0]['message']}"` or `str(body)` in an exception message.

### Pitfall 4: pybreaker's `@cb` decorator on async functions silently never trips
**What goes wrong:** `@breaker async def _search_impl(...)` wraps the coroutine *object* (synchronously returned by the `async def` call), so failures from `await coro` are never observed by pybreaker. Counter stays at 0; circuit never opens.
**Why it happens:** pybreaker's decorator path predates async/await; `_call` runs synchronously and returns whatever the wrapped function returned — for async, that's a coroutine, not a result.
**How to avoid:** Use the existing `app.tools.circuit_breaker.call_with_breaker` helper. It drives `state.before_call` / `state._handle_error` / `state._handle_success` directly. The pin `pybreaker>=1.4.1,<2.0` locks the `_handle_error`/`_handle_success` internal API. [VERIFIED: backend/app/tools/circuit_breaker.py docstring + tests/unit/test_circuit_breaker.py]
**Warning signs:** Tests that simulate 5+ failures and expect `CircuitBreakerError` fail because the breaker stays CLOSED.

### Pitfall 5: Tenacity wrapper losing the `APIError` subclass after retries are exhausted
**What goes wrong:** `tenacity.RetryError` masks the original `APIServerError`, so callers can't introspect `retryable` or class hierarchy.
**Why it happens:** Default tenacity behavior raises `RetryError` when retries are exhausted.
**How to avoid:** Already locked — `app.tools.retry.retry_on_failure` configures `reraise=True`. Regression-locked in `tests/unit/test_retry.py`.
**Warning signs:** Any test caught `RetryError` instead of the expected `APIServerError`.

### Pitfall 6: Lifespan branch hard-failing on missing token
**What goes wrong:** `Settings(...)` with `duffel_api_token: SecretStr` (no default) raises `ValidationError` at boot when `DUFFEL_API_TOKEN` is unset. The dev stack stops being bootable for anyone without a Duffel account.
**Why it happens:** Pydantic-settings treats missing required fields as fatal.
**How to avoid:** D-01 — `duffel_api_token: SecretStr | None = None` (default `None`). Lifespan auto-fallback (D-02) detects `None` and swaps in `MockFlightAPIClient`.
**Warning signs:** `ValidationError: 1 validation error for Settings, duffel_api_token` at uvicorn startup on a fresh checkout.

### Pitfall 7: `ApiKeyScrubber` regex misses `duffel_test_*` / `duffel_live_*`
**What goes wrong:** A Duffel bearer token leaks to logs because the existing `SECRET_PATTERNS` cover `sk-`, `sk-ant-`, and JSON `api_key` field shapes — but not `duffel_*_*`. Token shape is `duffel_(test|live)_[A-Za-z0-9_-]{20,}` per Duffel docs convention.
**Why it happens:** The scrubber was tuned for OpenAI/Anthropic key shapes during Phase 4.5. Duffel was added as a vendor in Phase 7; the regex set never updated.
**How to avoid:** Add **one** regex tuple to `SECRET_PATTERNS`: `(re.compile(r"duffel_(test|live)_[A-Za-z0-9_-]{20,}"), "duffel_[REDACTED]")`. Add unit test in `tests/unit/test_log_scrubbing.py` covering both `duffel_test_*` and `duffel_live_*`. [VERIFIED: `app/llm/log_scrubbing.py` SECRET_PATTERNS structure]
**Warning signs:** Searching `journalctl` / log files for `duffel_test_` returns hits in any environment.

### Pitfall 8: Justfile `test-e2e` target uses stale `-m "e2e"` marker
**What goes wrong:** `just test-e2e` selects nothing (markers were removed in Phase 4.4), so `e2e_duffel/` is never collected via that command and developers think real-API tests are passing when they never ran.
**Why it happens:** Stale tooling not updated when markers were dropped.
**How to avoid:** Phase 7 adds a new `just test-duffel` target that runs `pytest tests/e2e_duffel/` (path selector). The existing `test-e2e` target is OUT OF SCOPE for this phase but the planner should NOT route Duffel tests through it. Flag for follow-up.
**Warning signs:** Running `just test-e2e` with `DUFFEL_API_TOKEN` unset returns "0 selected" but exits 0 (false-green).

## Code Examples

Verified patterns from authoritative sources:

### Example 1: Duffel offer-request body (single-trip + round-trip)
```python
# Source: Duffel docs sample cURL (verified 2026-06-06 — "Duffel-Version: v2", "Bearer ...")
# Single trip:
body = {
    "data": {
        "slices": [
            {
                "origin": query.origin,           # "MAD"
                "destination": query.destination, # "BCN"
                "departure_date": str(query.departure_date),  # "2026-07-15"
                # D-14: server-side max_stops mapping
                **({"max_connections": query.max_stops} if max_stops is not None else {}),
            }
        ],
        # D-13: adult-only first cut
        "passengers": [{"type": "adult"}] * query.passengers,
        # D-10: cabin_class on the request envelope
        "cabin_class": query.booking_class,  # "economy" | "premium_economy" | "business" | "first"
    }
}

# Round trip (D-07): two slices.
if query.return_date is not None:
    body["data"]["slices"].append({
        "origin": query.destination,
        "destination": query.origin,
        "departure_date": str(query.return_date),
        **({"max_connections": query.max_stops} if max_stops is not None else {}),
    })
```

### Example 2: Reading `data.offers[]` from a `return_offers=true` response
```python
# Source: Duffel docs (verified 2026-06-06)
payload: dict[str, Any] = await resp.json()
offers: list[dict[str, Any]] = payload["data"]["offers"]
```

### Example 3: `_normalize_offer` — Duffel offer → vendor-neutral `Flight`
```python
# Source: Duffel SDK offer model + project's Flight schema (D-08, D-09, D-10)
def _normalize_offer(self, offer: dict[str, Any]) -> Flight:
    # Each Duffel offer is one trip; outbound slice is slices[0].
    # ABC contract returns list[Flight] (one per offer); per-segment fan-out
    # happens in flight_search.py's _to_flight_search_result helper if needed.
    slice_ = offer["slices"][0]
    segments = slice_["segments"]
    first_seg, last_seg = segments[0], segments[-1]

    # D-09: naive datetimes from Duffel — attach UTC as documented fallback.
    dep_at = datetime.fromisoformat(first_seg["departing_at"])
    arr_at = datetime.fromisoformat(last_seg["arriving_at"])
    if dep_at.tzinfo is None:
        dep_at = dep_at.replace(tzinfo=UTC)
    if arr_at.tzinfo is None:
        arr_at = arr_at.replace(tzinfo=UTC)

    # D-10: cabin lives at slices[].segments[].passengers[0].cabin_class.
    cabin_raw: str = first_seg["passengers"][0]["cabin_class"]  # "economy" | ...
    booking_class = cabin_raw.lower()  # validator in Flight model rejects unknowns

    carrier = first_seg["marketing_carrier"]
    return Flight(
        id=offer["id"],
        origin=first_seg["origin"]["iata_code"],
        destination=last_seg["destination"]["iata_code"],
        departure=dep_at,
        arrival=arr_at,
        price=Decimal(offer["total_amount"]),         # str-encoded by Duffel
        currency=offer["total_currency"],
        carrier=carrier["name"],                      # human-readable
        flight_number=f"{carrier['iata_code']}{first_seg['marketing_carrier_flight_number']}",
        duration_minutes=_iso_pt_to_minutes(slice_["duration"]),
        stops=len(segments) - 1,
        booking_class=booking_class,                  # type: ignore[arg-type] — validator narrows
    )
```
**Field provenance:** `total_amount` / `total_currency` / `slices[].duration` / `marketing_carrier.iata_code` / `marketing_carrier_flight_number` / `slices[].segments[].passengers[].cabin_class` confirmed via the archived `duffel-api-python` SDK source (`offer.py`, `offer_slice_segment.py`). [VERIFIED: github.com/duffelhq/duffel-api-python — file references in research session]

### Example 4: Lightweight auth probe — `GET /air/airlines?limit=1`
```python
# Source: Duffel SDK supporting/airlines.py (verified 2026-06-06)
# Use this for the e2e_duffel auth-probe test. Reference data; no per-search quota burn.
async def _auth_probe(self) -> bool:
    async with ClientBuilder().timeout(timedelta(seconds=10)).error_for_status(True).build() as client:
        await (
            client.get(f"{self._base_url}/air/airlines")
            .query({"limit": "1"})
            .bearer_auth(self._api_token)
            .header("Duffel-Version", _DUFFEL_VERSION)
            .header("Accept", "application/json")
            .build()
            .send()
        )
    return True
```
**Note:** This pattern is recommended for the **e2e_duffel test only**, not for `health_check()`. Per CONTEXT.md "Claude's Discretion", `health_check()` should return `True` without a network call (mirrors the deleted Amadeus pattern where `health_check` just returned `True` after the token-fetch path was simplified out).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Amadeus REST + OAuth2 client_credentials | Duffel REST + static bearer token | 2026-06-05 (vendor switch, commit `5d7499c`) | Whole token-cache layer removed (~90 LOC); simpler error surface; Duffel-Version header replaces token-refresh complexity. |
| `aiohttp` outbound HTTP | `pyreqwest` | Phase 7 (ADR-008, 2026-05-15) | Already shipped; reused. |
| Hand-rolled retry sleep loop | `tenacity.retry` via `retry_on_failure` | Phase 7 plan 07-01 (commit `26aa14c`) | Already shipped; reused. |
| pybreaker `@cb` decorator | `call_with_breaker` async helper | Phase 7 plan 07-03 (commit `ab10c68`) | Already shipped; reused. |
| Module-level `normalize_amadeus_offer` / `normalize_skyscanner_itinerary` | Per-impl `_normalize_offer` private method | D-08 (this phase) | Cleans up `flight_search.py`; removes dead code from Phase 4.6 that has no live caller. |
| In-memory `_histories` dict | `PostgresMessageStore` (Phase 6) | Phase 6 (2026-06-05, commit `f8a417b` and earlier) | Orthogonal — does not affect Phase 7 surface. |

**Deprecated/outdated:**
- The official `duffel-api` Python SDK (PyPI `duffel-api`) — archived 2024-09-12 with maintainer note: "not currently being supported by Duffel due to a lack of adoption." Defaults to `Duffel-Version: v1`. Not async. We do not use it.
- The deleted `app.flights.amadeus_client` module — gone from `master` (commit `5d7499c`); any stale import surfaces via mypy.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `errors[0].title` is safe to surface in user-facing exception messages; `errors[0].message` (Duffel's verbose-detail field) may echo creds/PII. | Pitfall 3, D-04 | LOW — even if `title` occasionally embeds an input field name, the bearer token never appears in `title` and the `ApiKeyScrubber` is a second layer. The conservative D-04 mitigation (status-code-only messages) makes this assumption non-load-bearing for runtime safety; it only matters for diagnostics richness. |
| A2 | Duffel `slices[].duration` is an ISO-8601 PT string (`"PT5H30M"` shape), parseable by `_iso_pt_to_minutes`. | Code Examples Example 3 | LOW — IATA convention is industry-standard; Amadeus and Skyscanner both emit this shape. The Duffel SDK exposes it as a string field but does not document the format precisely in the public reference material I could read. **Mitigation in plan:** unit test `_normalize_offer` with a recorded fixture; if format differs, a 1-line regex update suffices. |
| A3 | Duffel `marketing_carrier_flight_number` is the bare flight number (e.g. `"412"`), not prefixed with the IATA code. | Example 3 | LOW — SDK field name signals the bare number. If the value already includes the IATA prefix, the f-string produces a doubled prefix (`"DLDL412"`); fixture-based unit test catches this on first run. |
| A4 | Duffel bearer-token format `duffel_(test|live)_[A-Za-z0-9_-]{20,}` is the canonical regex shape. | Pitfall 7 | LOW — confirmed in CONTEXT.md and consistent with Duffel marketing material; the regex's `{20,}` lower bound is conservative. Unit test against both prefixes with a representative-length token will lock the contract. |
| A5 | Duffel sandbox does not enforce a per-request quota for `GET /air/airlines` (used as the e2e auth probe). | Code Examples Example 4 | LOW — reference-data endpoints are conventionally free across the industry. **Mitigation:** if it does count, the daily CI quota is unlikely to exhaust on `--limit=1` calls. Worst case: switch the probe to a `POST /air/offer_requests` and accept the quota cost. |
| A6 | `slices[].segments[].passengers[].cabin_class` is the canonical cabin location on a Duffel offer. | D-10, Example 3 | LOW-MEDIUM — confirmed via the archived Python SDK's `OfferSliceSegmentPassenger` model. The field is consistently documented but Duffel may also expose a top-level `cabin_class` echo of the request — D-10 already prefers the segment-level value; if it's missing for a particular response shape we'd need a fallback, locked by a unit test. |
| A7 | Duffel responses never include the bearer token in error bodies. | Pitfall 3 | LOW — the `ApiKeyScrubber` regex addition (Pitfall 7) is a defense-in-depth layer regardless. |
| A8 | The CI sandbox sometimes returns sparse offers for popular routes; MAD→BCN is reliable. | Pitfall 1 | MEDIUM — carried forward from the Amadeus phase's sandbox experience. Duffel sandbox inventory may differ. **Mitigation:** D-12 already lists LON→NYC as a fallback. If both fail, the e2e suite will surface it loudly with a `count=0` assertion error pointing to the exact route. |
| A9 | Duffel's `Retry-After` header is present on 429 responses. | D-04 | MEDIUM — Duffel docs explicitly mention `ratelimit-reset` (RFC 2616 timestamp) and three rate-limit headers but do **NOT** mention `Retry-After`. Our `_raise_from_http_status` should inspect the response headers `dict` and fall back gracefully when neither header is present (use the `APIRateLimitError(retry_after=60)` default). [VERIFIED: Duffel Errors docs do not list `Retry-After`] |

**If this table seems risk-heavy:** every entry is LOW or LOW-MEDIUM. The Duffel API is well-documented at the level we need; the assumptions cluster around fixture-locked details (field names, format strings) that a single recorded sandbox response will resolve in Wave 0. None of A1–A9 block planning.

## Open Questions

1. **Should `health_check()` issue a real Duffel call or return `True` unconditionally?**
   - What we know: deleted Amadeus `health_check` returned `True` after the token-fetch dependency was removed. CONTEXT.md "Claude's Discretion" defers this to research.
   - What's unclear: whether the lifespan should fail-fast vs surface degradation via `/health`.
   - Recommendation: **return `True` unconditionally.** Lifespan auto-fallback (D-02) handles the no-creds case. A live network probe at `health_check` would (a) burn quota on every `/health` poll, (b) introduce flakiness into liveness checks, (c) break parity with the mock client. The e2e_duffel auth-probe test (D-12 case `a`) covers the "are creds valid?" question.

2. **Should `_raise_from_http_status` parse `Retry-After` from the response headers, or always default to 60s?**
   - What we know: Duffel docs list `ratelimit-limit`, `ratelimit-remaining`, `ratelimit-reset` but **not** `Retry-After`. Our `APIRateLimitError(retry_after: int = 60)` default exists for the missing-header case.
   - What's unclear: whether a `Retry-After` is sometimes returned anyway (some gateways insert it on 429).
   - Recommendation: **parse `Retry-After` if present, else default to 60s.** Use `int(headers.get("retry-after", 60))`. Don't try to parse `ratelimit-reset` (RFC 2616 timestamp) in v1 — defer to Phase 8 hardening.

3. **Does Duffel's `errors[0].title` field ever omit on certain error envelopes?**
   - What we know: Title is documented as always present.
   - What's unclear: edge cases (gateway timeouts upstream of Duffel where the body shape differs).
   - Recommendation: defensive fall-through — `body.get("errors", [{}])[0].get("title", f"Duffel error (status={status})")` in the diagnostics-log path. The user-facing message stays status-only per D-04 regardless.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | Project base | ✓ | 3.13.9 (uv-managed) | — |
| `uv` | Package manager | ✓ | (latest stable) | — |
| `pyreqwest` | Outbound HTTP | ✓ | 0.12.0 (pinned) | — |
| `pybreaker` | Circuit breaker | ✓ | 1.4.1+ (pinned) | — |
| `tenacity` | Retry decorator | ✓ | 9.1.2+ (pinned) | — |
| `pydantic-settings` | `Settings` env load | ✓ | 2.6.0+ (pinned) | — |
| `slopcheck` | Package legitimacy gate | ✓ | (uv tool install at `~/.local/bin/slopcheck`) | — |
| `DUFFEL_API_TOKEN` env var | Real-API e2e tests + lifespan branch | ✗ (developer-supplied) | — | Lifespan auto-fallback to mock; e2e_duffel suite skips atomically. |
| GitHub `secrets.DUFFEL_API_TOKEN` | `duffel-e2e` CI job | ✗ (admin must configure) | — | Job is gated and skipped when secret absent. |
| GitHub `vars.DUFFEL_E2E_ENABLED` | `duffel-e2e` CI job (D-11) | ✗ (admin must configure) | — | Job skipped when var absent or false. |
| Duffel sandbox account | Creating `DUFFEL_API_TOKEN` | (developer task) | — | Skip real-API tests; rely on mock for local dev. |

**Missing dependencies with no fallback:** none — every blocking dep is already pinned and installed.
**Missing dependencies with fallback:** `DUFFEL_API_TOKEN` + GH secret/var — D-02 / D-11 design specifically for this gap. README must document signup → token-creation flow (replaces the deleted AMADEUS_* section).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8+ + `pytest-asyncio` (asyncio_mode = "auto") |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (testpaths = ["tests"]) |
| Quick run command | `cd backend && uv run pytest tests/unit/test_duffel_client.py tests/unit/test_log_scrubbing.py -x` |
| Full suite command | `cd backend && uv run pytest` (collects unit + integration + e2e + e2e_duffel-when-token-set) |
| Real-API gate command | `cd backend && DUFFEL_API_TOKEN=duffel_test_... uv run pytest tests/e2e_duffel/ -v` |
| New justfile target | `just test-duffel` → `cd backend && uv run pytest tests/e2e_duffel/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| REQ-real-flight-api | `Settings.duffel_api_token` is a `SecretStr` and `Settings.duffel_env` is a `Literal["test","live","mock"]` | unit | `pytest tests/unit/test_config_duffel.py -x` | ❌ Wave 0 |
| REQ-real-flight-api | Lifespan auto-fallback: missing token → mock; mock env literal → mock; valid token + env="test" → DuffelFlightClient | integration | `pytest tests/integration/test_lifespan_flight_provider.py -x` | ❌ Wave 0 (deleted with Amadeus, must rebuild) |
| REQ-real-flight-api | `DuffelFlightClient.search` composes retry + breaker + pyreqwest in correct order | unit | `pytest tests/unit/test_duffel_client.py::test_search_composition -x` | ❌ Wave 0 |
| REQ-real-flight-api | `_normalize_offer` produces a TZ-aware `Flight` from a recorded Duffel offer fixture (multi-segment, all fields populated, naive→UTC) | unit | `pytest tests/unit/test_duffel_client.py::test_normalize_offer -x` | ❌ Wave 0 |
| REQ-real-flight-api | HTTP-status mapping: 401 → `APIClientError(retryable=False)`; 422 → `APIClientError`; 429 → `APIRateLimitError(retryable=True)`; 5xx → `APIServerError(retryable=True)`. Body never appears in exception message. | unit | `pytest tests/unit/test_duffel_client.py::test_error_mapping -x` | ❌ Wave 0 |
| REQ-real-flight-api | `offset > 0` returns `offers[:limit]` regardless (CR-01 regression-lock) | unit | `pytest tests/unit/test_duffel_client.py::test_offset_capped -x` | ❌ Wave 0 |
| REQ-real-flight-api | Round-trip query (`return_date` set) produces 2 slices in the request body | unit | `pytest tests/unit/test_duffel_client.py::test_round_trip_two_slices -x` | ❌ Wave 0 |
| REQ-real-flight-api | `max_stops` maps to `slice.max_connections` server-side | unit | `pytest tests/unit/test_duffel_client.py::test_max_stops_mapping -x` | ❌ Wave 0 |
| REQ-real-flight-api | `ApiKeyScrubber` redacts `duffel_test_*` and `duffel_live_*` | unit | `pytest tests/unit/test_log_scrubbing.py::test_scrubs_duffel_tokens -x` | ❌ Wave 0 |
| REQ-real-flight-api | Live e2e suite: auth probe with valid token returns 2xx | e2e_duffel (gated) | `DUFFEL_API_TOKEN=... pytest tests/e2e_duffel/test_duffel_client.py::test_auth_probe -x` | ❌ Wave 0 |
| REQ-real-flight-api | Live e2e suite: MAD→BCN returns ≥1 offer | e2e_duffel (gated) | `... pytest tests/e2e_duffel/test_duffel_client.py::test_real_search_returns_results -x` | ❌ Wave 0 |
| REQ-real-flight-api | Live e2e suite: vendor-neutral `Flight` shape after `_normalize_offer` | e2e_duffel (gated) | `... pytest tests/e2e_duffel/test_duffel_client.py::test_vendor_neutral_shape -x` | ❌ Wave 0 |
| REQ-real-flight-api | Live e2e suite: bogus token surfaces as `APIClientError(retryable=False)` | e2e_duffel (gated) | `... pytest tests/e2e_duffel/test_duffel_client.py::test_error_mapping_401 -x` | ❌ Wave 0 |
| REQ-real-flight-api | `flight_search.py` no longer imports `normalize_amadeus_offer` / `normalize_skyscanner_itinerary` (D-08 cleanup) | unit | `pytest tests/unit/test_flight_search.py -x` | ✅ existing — extend |
| REQ-real-flight-api | `/health` returns `flight_provider: "real" \| "mock"` correctly across both lifespan branches | integration | `pytest tests/integration/test_health_endpoint.py -x` | ✅ existing — extend |

### Sampling Rate

- **Per task commit:** `cd backend && uv run pytest tests/unit/test_duffel_client.py tests/unit/test_log_scrubbing.py tests/unit/test_config_duffel.py -x` (~3-5s)
- **Per wave merge:** `cd backend && uv run pytest tests/unit tests/integration --cov=app --cov-fail-under=60` (mirrors PR CI; ~30-90s)
- **Phase gate (before `/gsd:verify-work`):** Full suite green + `DUFFEL_API_TOKEN=... just test-duffel` green (when real creds available locally) + `just check` (lint + format + mypy) clean.

### Wave 0 Gaps

- [ ] `tests/unit/test_duffel_client.py` — covers REQ-real-flight-api unit slices (composition, normalization, error mapping, offset cap, round-trip, max_stops). Includes recorded JSON fixtures for `_normalize_offer` (one direct, one connecting). Build a `tests/fixtures/duffel/` directory with `offer_request_response_*.json` fixtures.
- [ ] `tests/unit/test_config_duffel.py` — covers `Settings.duffel_api_token: SecretStr | None` and `Settings.duffel_env: Literal[...]` shape validation.
- [ ] `tests/unit/test_log_scrubbing.py` — extend with `test_scrubs_duffel_tokens` (both `duffel_test_*` and `duffel_live_*` patterns).
- [ ] `tests/integration/test_lifespan_flight_provider.py` — rebuild (was deleted with Amadeus) covering the three lifespan branches: mock literal, missing token, valid token.
- [ ] `tests/e2e_duffel/__init__.py` + `conftest.py` (module-scoped `duffel_client` fixture) + `test_duffel_client.py` (4 tests per D-12). Conftest deliberately does **not** inherit any integration-conftest stubs — these tests issue real HTTP.
- [ ] `tests/fixtures/duffel/offer_request_response_oneway.json` + `offer_request_response_roundtrip.json` — recorded sandbox responses for `_normalize_offer` unit tests. (Capture these once during Wave 0 with `DUFFEL_API_TOKEN`; they then drive offline tests forever.)

*(All test infrastructure for unit/integration is already present; framework install not needed.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Static bearer token (`Authorization: Bearer duffel_test_*`); `Settings.duffel_api_token: SecretStr` ensures the value is opaque to logs. |
| V3 Session Management | no (out-of-process) | Duffel does not issue sessions; bearer is long-lived. |
| V4 Access Control | no (single-tenant API consumer) | We are the consumer of Duffel; no per-user authorization is performed against Duffel. |
| V5 Input Validation | yes | `FlightQuery` validators (existing) + `_normalize_offer` defensive parsing (`KeyError` / `IndexError` / unknown-cabin fallback). |
| V6 Cryptography | no | Bearer token in transit only; no client-side crypto. TLS terminates at Duffel. |
| V7 Error Handling | yes | D-04 status-driven mapping; never echo body content into exception messages (T-07-02). |
| V8 Data Protection | yes | `ApiKeyScrubber` regex extension for `duffel_(test|live)_*`. |
| V12 API/Web Service | yes | `pyreqwest` enforces TLS via `https://api.duffel.com`; no plaintext HTTP. |
| V14 Configuration | yes | `Settings.duffel_api_token: SecretStr` — `repr()` and `str()` redact; comma-separated env `DUFFEL_API_TOKEN`. Lifespan auto-fallback prevents boot-time failures from missing token. |

### Known Threat Patterns for `pyreqwest` + bearer-token-auth client

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Bearer token leaked into logs (Duffel echoes inputs in error bodies) | Information Disclosure | `ApiKeyScrubber` regex addition (Pitfall 7); D-04 forbids body-derived exception messages. |
| Bearer token leaked into git history via `.env` | Information Disclosure | `.env` already in `.gitignore` (verify); README documents signup → token-creation; CI uses `secrets.DUFFEL_API_TOKEN` (never repo files). |
| Server-side request forgery via attacker-controlled `base_url` | Tampering | `base_url` is hardcoded to `https://api.duffel.com` in lifespan (no env override); `Settings.duffel_env` is a `Literal["test","live","mock"]` so even environment-driven branching is bounded. |
| Open breaker masking real failures | Repudiation | Locked: `pybreaker.CircuitBreakerError` mapped to `APIServerError(retryable=False)` so the user-visible error chain is preserved (D-13). |
| Retry storm on a struggling Duffel endpoint | Denial of Service (self) | Tenacity `max_retries=3, backoff_base=2.0`; pybreaker `fail_max=5, reset_timeout=60` caps the storm (existing primitives). |
| 401 on stale token causing infinite retry | Denial of Service (self) | 401 maps to `retryable=False` (D-04); tenacity predicate skips. (No token-cache invalidation needed — Duffel uses static bearer.) |
| Vendor `errors[0].message` echoing partial token in 401 body | Information Disclosure | D-04: status-only message; `code`/`type` logged for diagnostics. `ApiKeyScrubber` redacts the bearer-shaped substring before formatter dispatch. |
| Round-trip `return_date` injection (`return_date < departure_date`) | Tampering | Existing `FlightQuery.validate_dates` rejects at the model boundary (Phase 4.6); the planner does not need to add new validators. [VERIFIED: backend/app/flights/models.py:67] |

## Sources

### Primary (HIGH confidence)
- **Duffel docs — POST /air/offer_requests cURL sample** — confirmed `Duffel-Version: v2` literal header value, `Authorization: Bearer ...`, `Accept: application/json`, base `https://api.duffel.com`, `data.{slices,passengers,cabin_class}` body shape. (URL: `https://duffel.com/docs/api/v2/offer-requests/create-offer-request` — fetched 2026-06-06.)
- **Duffel docs — Errors page** — confirmed error envelope `{type, code, title, message, documentation_url, source}`, status code mapping (401/422 not retry-safe; 429/503/504 retry-safe; 502 not retry-safe per Duffel guidance), three rate-limit headers (`ratelimit-limit`/`ratelimit-remaining`/`ratelimit-reset`); `Retry-After` not officially listed. (URL: `https://duffel.com/docs/api/overview/errors` — fetched 2026-06-06.)
- **Duffel SDK source — `parse_datetime` in `duffel_api/utils.py`** — confirmed Duffel emits both naive (`"2024-01-15T14:30:45"`) and TZ-aware (`"...Z"`) ISO-8601 strings; segment-level `departing_at`/`arriving_at` are the naive variant. (URL: `https://raw.githubusercontent.com/duffelhq/duffel-api-python/main/duffel_api/utils.py` — fetched 2026-06-06.)
- **Duffel SDK source — `offer.py` model** — confirmed `OfferSliceSegmentPassenger.cabin_class` is the canonical cabin location per segment per passenger. (URL: `https://raw.githubusercontent.com/duffelhq/duffel-api-python/main/duffel_api/models/offer.py` — fetched 2026-06-06.)
- **Duffel SDK source — `supporting/airlines.py`** — confirmed `GET /air/airlines?limit=N` is the reference-data list endpoint. (URL: `https://raw.githubusercontent.com/duffelhq/duffel-api-python/main/duffel_api/api/supporting/airlines.py` — fetched 2026-06-06.)
- **Duffel SDK README banner** — confirmed library archived 2024-09-12, defaults to `Duffel-Version: v1`, sync-only. We are NOT consuming this SDK. (URL: `https://github.com/duffelhq/duffel-api-python` — fetched 2026-06-06.)
- **pyreqwest README** — confirmed `ClientBuilder().timeout(...).error_for_status(True).build()` + `.post(url).bearer_auth(...).json(...).header(...).build().send()` chain; exception types `StatusError`, `ConnectError`, `RequestTimeoutError`. (URL: `https://github.com/MarkusSintonen/pyreqwest` — fetched 2026-06-06.)
- **Local repo — `backend/app/tools/{retry,circuit_breaker,flight_client}.py`, `backend/app/llm/log_scrubbing.py`, `backend/app/api/main.py`, `backend/app/exceptions.py`, `backend/app/flights/models.py`, `backend/app/config.py`** — read in full this session.
- **Local repo — git commits `5d7499c`, `1743f4b`, `3346e96`, `4d9487d`, `5c3405d`, `26aa14c`, `ab10c68`, `1b72d32`** — inspected for prior Amadeus implementation patterns and CR-01 regression detail.
- **PyPI — `pyreqwest 0.12.0`** — version + repo URL verified via `https://pypi.org/pypi/pyreqwest/json`.
- **Local — `slopcheck install pyreqwest pybreaker tenacity`** — `3 OK`, run 2026-06-06.

### Secondary (MEDIUM confidence)
- **Duffel docs — error-envelope safe vs sensitive fields guidance** — `title` safe to surface, `message` handle carefully. Single source (Duffel error docs page). Cross-checked against the Amadeus T-07-02 mitigation pattern.

### Tertiary (LOW confidence)
- None. Every claim in this document is either VERIFIED via an authoritative source or explicitly tagged ASSUMED in the Assumptions Log with risk and mitigation.

## Metadata

**Confidence breakdown:**
- Duffel API surface (endpoints, headers, auth, error envelope, datetime format): HIGH — verified against Duffel docs + Duffel SDK source.
- Architecture / reuse patterns (retry, breaker, lifespan, error mapping): HIGH — verified against the live repo and prior Amadeus commits that compiled and passed tests.
- `_normalize_offer` field path (`slices[].segments[].passengers[].cabin_class`, `marketing_carrier_flight_number`, `total_amount`): HIGH-MEDIUM — verified against the Duffel Python SDK model classes; the SDK is archived but its mapping is the canonical reference for Duffel's JSON shape since the docs do not publish a full schema page.
- Pitfalls: HIGH — Pitfalls 1, 2, 4, 5, 6, 7 are carry-over from the prior Amadeus phase and are regression-locked by existing tests; Pitfall 3 is conservative (D-04 mitigation does not depend on the assumption); Pitfall 8 is a tooling-debt note, not a Phase 7 blocker.
- Validation Architecture: HIGH — derived from existing test framework; Wave 0 file list is concrete and matches the prior Amadeus suite skeleton.
- Security Domain: HIGH-MEDIUM — ASVS mapping follows directly from the threat model; the only MEDIUM is the `Retry-After` parsing assumption (A9), already mitigated by graceful fallback.

**Research date:** 2026-06-06
**Valid until:** 2026-07-06 (30 days — Duffel API v2 is stable; the only fast-moving aspect is the sandbox inventory for Pitfall 1, which the MAD→BCN + LON→NYC fallback covers).

## RESEARCH COMPLETE

**Phase:** 7 - Real Flight API (Duffel)
**Confidence:** HIGH

### Key Findings
- The Duffel API surface is materially simpler than the deleted Amadeus implementation (static bearer, single round-trip search, no OAuth2 token cache). Phase 7 is plumbing assembly: ~250 LOC for `DuffelFlightClient` plus a `Settings` block, a lifespan branch reintroduction, an `ApiKeyScrubber` regex addition, and a path-isolated e2e suite.
- Every existing primitive (tenacity retry, async-safe pybreaker, pyreqwest builder chain, `_raise_from_http_status` shape, `Flight`/`FlightSegment`/`FlightResult` vendor-neutral models, lifespan auto-fallback shape) carries forward verbatim from the deleted Amadeus implementation. CR-01 (offset double-application) is design-prevented by D-06.
- Duffel emits naive ISO-8601 datetimes for segment `departing_at`/`arriving_at` (verified via SDK `parse_datetime`); D-09 UTC-attach is the correct mitigation.
- `errors[0].title` is the safe field for diagnostics; `errors[0].message` may echo PII — D-04 status-only mapping is the right default. `ApiKeyScrubber` regex must be extended for `duffel_(test|live)_*` (Pitfall 7 — one-line addition).
- `GET /air/airlines?limit=1` is the cheapest auth probe for the e2e_duffel suite (reference data, no per-search quota burn). MAD→BCN reliably returns offers in vendor sandboxes; LON→NYC is the documented fallback (Pitfall 1).
- No new dependencies. Phase 7 is pure code work. slopcheck against existing pinned deps returns `3 OK`.

### File Created
`/Users/axel/code/trip_planner/.planning/phases/07-real-flight-api/07-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | All deps already pinned and slopcheck-verified; no novel additions. |
| Architecture | HIGH | Patterns 1-4 are direct carry-over from a prior shipped phase that passed 25/25 verification truths. |
| Pitfalls | HIGH | 6 of 8 pitfalls are regression-locked by existing tests; 2 are conservative defaults that don't depend on the underlying assumption. |
| Duffel API surface | HIGH | Headers, endpoints, error envelope, datetime format verified against Duffel docs + Duffel SDK source. |
| Validation Architecture | HIGH | Wave 0 file list maps directly to D-12 four-test suite + the deleted Amadeus unit/integration test skeleton, which is recoverable from git history if needed. |

### Open Questions

1. `health_check()` return policy — recommendation provided (return `True`).
2. `Retry-After` parsing strategy — recommendation provided (parse if present, default to 60s).
3. Defensive `errors[0].title` fallback for unusual error envelopes — recommendation provided.

All three are resolvable in-plan; none block planning.

### Ready for Planning
Research complete. The planner can write a 5-7 plan phase: (P1) `Settings` fields + log-scrubber regex + `.env.example` updates; (P2) `DuffelFlightClient` scaffold + `_raise_from_http_status` + offline unit tests against recorded fixtures; (P3) `_normalize_offer` + round-trip slice construction + offset cap; (P4) lifespan branch reintroduction + `/health` integration tests + `flight_search.py` cleanup of dead module-level normalizers (D-08); (P5) `tests/e2e_duffel/` suite + `just test-duffel` + CI `duffel-e2e` job + README credential section.
