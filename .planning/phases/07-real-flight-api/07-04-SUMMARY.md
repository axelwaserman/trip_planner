---
phase: 07-real-flight-api
plan: 04
subsystem: backend/flights
tags: [amadeus, pyreqwest, oauth2, retry, circuit-breaker, token-cache, async]

# Dependency graph
requires:
  - phase: 07-real-flight-api
    provides: Plan 01 — `retry_on_failure` tenacity wrapper (`backend/app/tools/retry.py`)
  - phase: 07-real-flight-api
    provides: Plan 02 — `Settings.amadeus_env` / `amadeus_api_key` / `amadeus_api_secret` (`backend/app/config.py`)
  - phase: 07-real-flight-api
    provides: Plan 03 — async-safe `call_with_breaker` (`backend/app/tools/circuit_breaker.py`)
provides:
  - "AmadeusFlightClient(FlightAPIClient): concrete client implementing all four ABC methods (search, health_check, get_flight_details, check_availability)"
  - "OAuth2 client_credentials token cache with proactive 60s refresh + per-instance asyncio.Lock (D-01/D-02)"
  - "search() composition: @retry_on_failure outside, call_with_breaker inside, pyreqwest GET innermost (D-12)"
  - "HTTP status -> APIError mapping helper `_raise_from_http_status` (D-11)"
  - "Open-breaker -> APIServerError(retryable=False) so tenacity does not retry into open breaker (D-13)"
  - "Pitfall 2 fix: normalize_amadeus_offer attaches UTC when departure/arrival are naive (additive over Phase 4.6)"
  - "13 regression-locked unit tests across token cache concurrency, HTTP error mapping, search composition, and TZ handling"
affects: [07-05, 07-06]

# Tech tracking
tech-stack:
  added: [pyreqwest>=0.12.0]
  patterns:
    - "OAuth2 token cache with double-checked locking under asyncio.Lock (07-RESEARCH Pattern 1)"
    - "Retry-outside / breaker-inside composition via private decorated method (D-12)"
    - "Sandbox-permissive cabin fallback: unknown cabin codes log warning + degrade to 'economy' (Plan 06 e2e note)"
    - "TYPE_CHECKING-guarded imports + `from __future__ import annotations` to satisfy ruff TC001/TC003"

key-files:
  created:
    - backend/app/flights/amadeus_client.py
    - backend/tests/unit/test_amadeus_client.py
    - backend/tests/unit/test_amadeus_token_cache.py
    - backend/tests/unit/test_amadeus_error_mapping.py
  modified:
    - backend/app/tools/flight_search.py
    - backend/pyproject.toml
    - backend/uv.lock

key-decisions:
  - "BookingClass fallback policy: unknown cabin codes (anything outside the 4 IATA literals after lowercasing) fall back to 'economy' with logger.warning. Sandbox-permissive — Amadeus has been observed to surface non-IATA strings in test mode. No raise; degraded result is preferable to a hard 422."
  - "_apply_filters / _sort_flights inlined as module-level free functions in amadeus_client.py rather than extracted from MockFlightAPIClient. Rationale: MockFlightAPIClient's versions are instance methods on a different concrete class; extracting would require refactoring two files in scope of one plan. The free-function copies are 7 lines each and accept pure params — safe to keep duplicated until Phase 8 (where a third client may justify a shared utility module)."
  - "Composition order achieved via private decorated method `_fetch_with_retry_breaker` instead of decorating the public `search`. Reason: applying `@retry_on_failure` directly to an ABC method changes mypy's view of the return type from `Coroutine[Any, Any, list[Flight]]` (declared on FlightAPIClient.search) to `Awaitable[list[Flight]]` (tenacity's wrapper signature), tripping mypy strict's `[override]` check. Splitting into `search()` (public, plain async) -> `_fetch_with_retry_breaker()` (decorated, private) preserves the ABC contract and the composition order: retry-outside / breaker-inside / pyreqwest-innermost (D-12). Each retry attempt still re-checks the breaker because the decorator wraps the method that calls call_with_breaker."
  - "Pitfall 2 fix lives in BOTH `normalize_amadeus_offer` (Phase 4.6 path used by future structured-result callers) AND `AmadeusFlightClient._parse_flight_offers` (Plan 04 path that builds Flight directly). Single source of truth would require a small `_attach_utc_if_naive` helper, but copy-paste of the two-line `if .tzinfo is None: ... = .replace(tzinfo=UTC)` was lighter-weight and equally testable. The two callers diverged from each other on field shape (FlightResult vs Flight) before this fix, and continuing that divergence is consistent with the plan's interface decision."

requirements-completed: [REQ-real-flight-api]

# Metrics
duration: ~25min
completed: 2026-06-05
---

# Phase 07 Plan 04: AmadeusFlightClient Summary

**Implemented the real `AmadeusFlightClient` — the deliverable of REQ-real-flight-api. The client subclasses `FlightAPIClient`, performs OAuth2 client_credentials token fetch via pyreqwest with an in-process cache + concurrent-refresh `asyncio.Lock` (D-01/D-02), composes the Plan 01 retry decorator over the Plan 03 circuit breaker over a pyreqwest GET against `/v2/shopping/flight-offers` (D-12), maps Amadeus HTTP status codes onto the existing `APIError` hierarchy (D-11), and reuses the Phase 4.6 `normalize_amadeus_offer()` with the Pitfall-2 UTC fallback fix.**

## Performance

- **Started:** 2026-06-05 (post Plan 03)
- **Completed:** 2026-06-05
- **Tasks:** 3
- **Files created:** 4 (`amadeus_client.py` + 3 test files)
- **Files modified:** 3 (`flight_search.py`, `pyproject.toml`, `uv.lock`)
- **Tests added:** 13 (3 token cache + 6 parametrized error mapping + 4 search/parse)

## Tasks Executed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add pyreqwest dep + AmadeusFlightClient skeleton with token cache + error mapper | `3346e96` | `pyproject.toml`, `uv.lock`, `app/flights/amadeus_client.py` (created) |
| 2 | Implement AmadeusFlightClient.search composing retry+breaker+pyreqwest, plus naive-TZ fix in normalize_amadeus_offer | `1743f4b` | `app/flights/amadeus_client.py`, `app/tools/flight_search.py` |
| 3 | Add unit tests — token cache concurrency, error mapping, and search composition | `7b726bb` | `tests/unit/test_amadeus_client.py`, `tests/unit/test_amadeus_token_cache.py`, `tests/unit/test_amadeus_error_mapping.py` (all created) |

## Output Notes (per `<output>` directive in PLAN.md)

### BookingClass fallback policy

Unknown cabin codes returned by Amadeus fall back to `"economy"` with a `logger.warning` rather than raising. This is **permissive by design** because Amadeus sandbox has been observed to return non-IATA cabin strings (e.g. `"PREMIUM"` instead of `"PREMIUM_ECONOMY"`). The four valid `BookingClass` literal values are matched case-insensitively (`.lower()` before comparison); anything else degrades to `economy`. Verified by `test_unknown_cabin_falls_back_to_economy` against `"MYSTERY_CABIN"`, the four happy-path codes, and a missing-field offer.

**Plan 06 e2e note:** Live Amadeus may surface unexpected cabin strings the sandbox doesn't. The current policy logs the unknown code at WARNING level so anomalies surface in production without breaking flight rendering. If a Phase 8 follow-up wants to harden this, the right move is to expose the raw cabin string on `Flight` (or extend `BookingClass` literally) — not to start raising.

### `_apply_filters` / `_sort_flights` location

Inlined as module-level free functions inside `amadeus_client.py`, not shared with `MockFlightAPIClient`. Rationale: the mock's versions are instance methods, and extracting them would require touching `flight_client.py` (out of scope for this plan). The functions are pure (`list[Flight] + filter params -> list[Flight]`), 7 lines each, and have no behavioural divergence from the mock implementation. Phase 8 may extract a shared `app.flights.filters` module if a third client lands.

### Composition order verification

`@retry_on_failure(max_retries=3, backoff_base=2.0)` decorates `_fetch_with_retry_breaker`, whose body wraps `call_with_breaker(self._breaker, self._search_impl, ...)`. The public `search()` calls `_fetch_with_retry_breaker(...)` and then applies `_apply_filters` -> `_sort_flights` -> pagination slice on the returned list. This means:

1. **Retry is outside the breaker.** Each retry attempt re-evaluates `before_call` on the breaker, so a retry into an open breaker fails fast via `CircuitBreakerError` -> `APIServerError(retryable=False)` rather than re-issuing an HTTP call.
2. **Breaker is outside the HTTP call.** A 401 / 5xx that maps to `APIError(retryable=True)` is counted by the breaker via `state._handle_error`. Five consecutive failures (default `fail_max=5`) trip the breaker.
3. **HTTP is innermost.** `_search_impl` is the pyreqwest GET — naive of retry / breaker concerns.

Regression-locked by `test_circuit_breaker_open_raises_apiservererror_not_retried` (D-13) and `test_search_401_invalidates_token_cache` (T-07-04 / OQ-1).

## Verification Performed

- `uv run mypy app/flights/amadeus_client.py app/tools/flight_search.py` — strict, no errors.
- `uv run ruff check app/flights/amadeus_client.py app/tools/flight_search.py tests/unit/test_amadeus*.py` — clean.
- `uv run pytest tests/unit/test_amadeus_client.py tests/unit/test_amadeus_token_cache.py tests/unit/test_amadeus_error_mapping.py -v` — **13/13 passed.**
- `uv run pytest tests/unit/test_tool_json_normalization.py -v` — **12/12 passed** (Phase 4.6 normalization tests still green after Pitfall 2 additive fix).
- `uv run pytest tests/unit/ -x --tb=short` — **286 passed, 1 skipped** (full unit suite green).
- Smoke test: `AmadeusFlightClient('k','s','https://test.api.amadeus.com')` instantiates cleanly; `_token_lock` is an `asyncio.Lock` instance variable; `_raise_from_http_status` matrix verified across 5 status codes.

## Threat-Model Alignment

| Threat | Status | Where verified |
|--------|--------|----------------|
| T-07-02 (Information Disclosure — token refresh failure path) | Mitigated | `_refresh_token` constructs the wrapped `APIError` message from `type(exc).__name__` only — never the formatted exception text. Inline comment cites T-07-02. The credentials live in SecretStr (Plan 02) and are unwrapped only at call-time. |
| T-07-03 (Information Disclosure — non-token error logging) | Mitigated | `_raise_from_http_status` constructs error messages from `status` only — never the response body. Verified by parametrized `test_raise_from_http_status` across 6 codes. |
| T-07-04 (DoS — 401 token-refresh loop) | Mitigated | `_search_impl`'s 401 branch invalidates the cache (`_access_token = None`, `_expires_at = datetime.min`) BEFORE raising `APIClientError(retryable=False)`. Tenacity will NOT auto-retry; the next user-driven call gets a fresh token. Verified by `test_search_401_invalidates_token_cache`. The pybreaker layer caps any runaway against any failure mode (Plan 03 / `test_circuit_breaker_open_raises_apiservererror_not_retried`). |
| T-07-SC (Supply chain — pyreqwest install) | Mitigated | `pyreqwest>=0.12.0` matches RESEARCH.md's vetted entry (`OK`, ~1 yr old, source repo `MarkusSintonen/pyreqwest`). Inline rationale comment in `pyproject.toml` cites D-10/ADR-008 and explicitly documents the forbidden alternatives (`aiohttp`, `httpx`, `requests`). |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] mypy strict `[override]` clash on `@retry_on_failure` directly on `search`**

- **Found during:** Task 2, first `mypy` run after wiring the decorator on the public `search` method.
- **Issue:** Decorating `async def search(...) -> list[Flight]` with `@retry_on_failure(...)` changes the return type that mypy sees from `Coroutine[Any, Any, list[Flight]]` (the ABC's declared return type) to `Awaitable[list[Flight]]` (tenacity's `Callable[P, Awaitable[R]]` wrapper). Strict mypy flagged the override as incompatible.
- **Fix:** Split into `search()` (public, plain `async def`, no decorator — preserves ABC compatibility) and `_fetch_with_retry_breaker()` (private, decorated, contains the breaker invocation). Composition order is unchanged: retry-outside, breaker-inside, HTTP-innermost. Documented in the public `search` docstring + decisions section.
- **Files modified:** `app/flights/amadeus_client.py`.
- **Verification:** mypy strict clean; behaviour unchanged (verified by `test_circuit_breaker_open_raises_apiservererror_not_retried` which exercises the full retry+breaker composition through `search()`).
- **Committed in:** `1743f4b`.

**2. [Rule 3 — Blocking] ruff TC001/TC003 unused-runtime-import flags on Task 1 imports**

- **Found during:** Task 1 first `ruff check`.
- **Issue:** Task 1 imports several types (`Decimal`, `Flight`, `FlightQuery`, `SortBy`, `BookingClass`) that are used as annotations in Task 1 but only used at runtime in Task 2. With `from __future__ import annotations` active, all annotations are strings, so ruff's TC001/TC003 rules flagged them as type-checking-only imports. Additionally, the `_VALID_BOOKING_CLASSES` constant introduced in Task 1 was unused (Task 2 inlines the literal match).
- **Fix:** Moved annotation-only types into a `TYPE_CHECKING:` block in Task 1 (`Decimal`, `Flight`, `FlightQuery`, `SortBy`); deleted the unused `_VALID_BOOKING_CLASSES` constant. Task 2 then re-imported `Decimal` / `Flight` to runtime scope (because they are constructed at runtime inside `_search_impl` and `_parse_flight_offers`) and added `BookingClass` to TYPE_CHECKING (only used as a return annotation on `_extract_booking_class`).
- **Files modified:** `app/flights/amadeus_client.py` (in Task 1 commit).
- **Verification:** ruff clean across both tasks; mypy strict clean.
- **Committed in:** `3346e96` and `1743f4b`.

**3. [Rule 3 — Blocking] mypy strict literal-type clash on `Flight.booking_class`**

- **Found during:** Task 2 mypy run.
- **Issue:** `_extract_booking_class` returned `str` but `Flight.booking_class` expects `BookingClass = Literal[...]`. Strict mypy refused the assignment.
- **Fix:** Refactored `_extract_booking_class` from a generic `if normalized in {...}: return normalized` form (which mypy can't narrow to the literal type) to four explicit `if normalized == "<literal>": return "<literal>"` arms. Each arm narrows the return type correctly. Function return annotation upgraded to `BookingClass`.
- **Files modified:** `app/flights/amadeus_client.py`.
- **Verification:** mypy strict clean; `test_unknown_cabin_falls_back_to_economy` exercises all four happy paths plus the fallback.
- **Committed in:** `1743f4b`.

**4. [Rule 3 — Blocking] ruff SIM117 nested-`with` flag in test_amadeus_client.py**

- **Found during:** Task 3 ruff check.
- **Issue:** `test_circuit_breaker_open_raises_apiservererror_not_retried` originally used three nested `with` statements (patch.object + patch + pytest.raises). Ruff's SIM117 wanted them combined.
- **Fix:** Combined the two `patch` calls into a single `with (..., ...):` parenthesized form per PEP 617. Kept the inner `pytest.raises` blocks separate for readability of the assertion-per-call structure.
- **Files modified:** `tests/unit/test_amadeus_client.py`.
- **Verification:** ruff clean; test still passes.
- **Committed in:** `7b726bb`.

---

**Total deviations:** 4 auto-fixed (all Rule 3 blocking lint/type-check issues; no behavioural changes).
**Impact on plan:** Zero behavioural drift. The composition split (deviation #1) is structurally equivalent — retry-outside, breaker-inside, HTTP-innermost still holds. The other three are surface-level lint/type adjustments. All acceptance criteria pass.

## Issues Encountered

- The Postgres-backed integration tests (20 errors in `tests/integration/db/`) fail in this worktree because the docker compose stack isn't running — pre-existing environmental issue, not caused by this plan. Plan-level verification step 6 is therefore **partially deferred** to phase wrap-up (when the orchestrator can re-run the integration suite against the live compose stack). The plan-relevant test (`test_tool_json_normalization.py`) passes 12/12, confirming the Pitfall 2 fix is additive.

## Known Stubs

- `get_flight_details(flight_id)` raises `FlightSearchError` always — Amadeus has separate `/v2/shopping/flight-offers/pricing` and `/v2/schedule/flights` endpoints which CONTEXT.md scopes out of REQ-real-flight-api. Documented in the docstring.
- `check_availability(flight_id)` returns `True` always — Amadeus has no per-offer availability check distinct from re-running search. Documented in the docstring. v1 contract.

Both stubs are intentional and within plan scope; Plan 05 / 06 do not depend on them.

## User Setup Required

None for this plan. Plan 05 will require:
- Real Amadeus sandbox credentials in `AMADEUS_API_KEY` / `AMADEUS_API_SECRET` env vars (Plan 02 added the SecretStr-wrapped Settings fields).
- Plan 05's lifespan branch will instantiate `AmadeusFlightClient(api_key=..., api_secret=..., base_url=base_url)` where `base_url` is mapped from `Settings.amadeus_env`.

## Next Phase Readiness

- **Plan 05 unblocked:** the lifespan can call `AmadeusFlightClient(api_key=key.get_secret_value(), api_secret=secret.get_secret_value(), base_url=base_url)` and stash it on `app.state.flight_client` with no further code changes here. The ABC contract is fully satisfied.
- **Plan 06 unblocked:** the e2e_amadeus tests can exercise the live client via the existing `FlightAPIClient` injection point. The Pitfall 2 fix means naive Amadeus datetimes won't trip pydantic on `FlightEndpoint.at`.
- **No blockers carried forward.**

## Self-Check

Verifying claims before completion:

- `backend/app/flights/amadeus_client.py` — FOUND (566 lines).
- `backend/app/tools/flight_search.py` — FOUND with `tzinfo is None` Pitfall 2 fix at lines 183-188.
- `backend/tests/unit/test_amadeus_client.py` — FOUND (4 tests).
- `backend/tests/unit/test_amadeus_token_cache.py` — FOUND (3 tests).
- `backend/tests/unit/test_amadeus_error_mapping.py` — FOUND (1 parametrized test, 6 cases).
- `backend/pyproject.toml` — FOUND with `pyreqwest>=0.12.0` and rationale comment at lines 30-32.
- Commit `3346e96` (Task 1 — feat) — FOUND in `git log`.
- Commit `1743f4b` (Task 2 — feat) — FOUND in `git log`.
- Commit `7b726bb` (Task 3 — test) — FOUND in `git log`.
- `uv run mypy app/flights/amadeus_client.py app/tools/flight_search.py` — strict pass.
- `uv run ruff check app/flights/amadeus_client.py app/tools/flight_search.py tests/unit/test_amadeus*.py` — clean.
- All 13 new tests + 12 Phase 4.6 normalization tests + 286-test full unit suite all green.

## Self-Check: PASSED

---
*Phase: 07-real-flight-api*
*Plan: 04*
*Completed: 2026-06-05*
