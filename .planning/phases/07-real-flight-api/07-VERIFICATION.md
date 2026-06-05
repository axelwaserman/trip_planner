---
phase: 07-real-flight-api
verified: 2026-06-05T12:00:00Z
status: human_needed
score: 25/25 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 23/25
  gaps_closed:
    - "D-11: HTTP status mapping holds end-to-end — 401 surfaces as APIClientError(retryable=False), not a generic retryable APIError"
    - "AmadeusFlightClient.search returns correct results for all valid offset values"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Real Amadeus sandbox token fetch + search end-to-end"
    expected: "With AMADEUS_API_KEY + AMADEUS_API_SECRET set, `just test-amadeus` runs all four e2e_amadeus tests and they pass against the live sandbox: token fetched, MAD→BCN search returns ≥1 result, vendor-neutral fields populated, bad-credentials path raises APIClientError with retryable=False (newly tightened by Plan 07-07)."
    why_human: "Requires real Amadeus sandbox credentials and live HTTPS; out of scope for grep-based verification."
  - test: "/health surfaces flight_provider='real' under real credentials"
    expected: "With AMADEUS_API_KEY + AMADEUS_API_SECRET set in the running shell, `curl http://localhost:8000/health` returns `{\"status\":\"healthy\",\"flight_provider\":\"real\"}` (currently grep-verified in mock fallback only)."
    why_human: "Requires running the FastAPI app with live credentials; observable in CI but not in the verification harness."
  - test: "WARN log line emits exactly when AMADEUS_ENV is non-mock and creds are missing"
    expected: "Booting the backend with AMADEUS_ENV=test and no AMADEUS_API_KEY / AMADEUS_API_SECRET emits exactly one WARN containing the substring `AMADEUS_* creds missing`. Asserted programmatically by tests/integration/test_lifespan_flight_provider.py via caplog, but the human should sanity-check that it appears in the actual app output too."
    why_human: "Log routing in production environments is configurable; the test only verifies the logger emit, not the deployed sink."
  - test: "Pitfall 1 — sandbox sparse routes"
    expected: "MAD→BCN returns ≥1 offer in the live sandbox; if it does not, swap to LON→NYC per Plan 06 output guidance."
    why_human: "Sandbox content is operationally variable; the test is brittle without a human override path."
---

# Phase 7: Real Flight API Verification Report (Re-verification after Plan 07-07)

**Phase Goal:** Real Flight API — Amadeus client behind existing `FlightAPIClient` ABC; outbound HTTP via `pyreqwest`; reuse retry + circuit breaker + `APIError` hierarchy; gated integration tests.
**Verified:** 2026-06-05
**Status:** human_needed (all 25 truths VERIFIED; awaiting live-sandbox human checks)
**Re-verification:** Yes — supersedes the prior `gaps_found` report (23/25). Plan 07-07 closed both BLOCKERS (CR-01 + CR-02) without regressions.

## Re-verification Summary

The prior report flagged two BLOCKER defects in `backend/app/flights/amadeus_client.py`:

- **CR-01:** Pagination offset double-applied — `_search_impl` requested `max=str(limit)` ignoring offset, then `search()` sliced `[offset : offset + limit]`, silently dropping results for any `offset > 0`.
- **CR-02:** `_refresh_token` masked 401 responses as retryable — the catch-all `except Exception` wrapped a `KeyError("access_token")` (raised because the 401 body lacks `access_token`) into `APIError(retryable=True)`, so tenacity retried 3× against bad credentials. The e2e test regression-locked the bug by asserting only `pytest.raises(APIError)`.

Both are now fixed at HEAD with regression locks at the unit level (and at the e2e level for CR-02). Truths #17 and #25 upgrade FAILED → VERIFIED.

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                                                                | Status     | Evidence                                                                                                                                                                                                                                                                                       |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | D-10: `retry_on_failure` is implemented via `tenacity`, no hand-rolled `asyncio.sleep` loop, public signature preserved 1:1                          | ✓ VERIFIED | `backend/app/tools/retry.py` imports `tenacity.retry`; signature `retry_on_failure(max_retries, backoff_base, exceptions)` preserved.                                                                                                                                                          |
| 2   | D-10: tenacity `RetryError` never escapes — original `APIError` subclass surfaces (regression-locked by `reraise=True`)                              | ✓ VERIFIED | `reraise=True` at retry.py:77; `test_retry_raises_original_exception_not_retry_error` exists and passes.                                                                                                                                                                                       |
| 3   | D-10: Defaults preserved — `max_retries=3`, `wait_exponential(multiplier=backoff_base=2.0)`, `retry_if_exception(retryable=True predicate)`          | ✓ VERIFIED | retry.py:33-36 defaults, predicate at line 71 mirrors hand-rolled semantics exactly.                                                                                                                                                                                                           |
| 4   | `tenacity>=9.1.2` declared in `[project] dependencies`                                                                                               | ✓ VERIFIED | `backend/pyproject.toml:29`.                                                                                                                                                                                                                                                                   |
| 5   | D-04: `Settings.amadeus_env: Literal['test','prod','mock'] = 'test'`                                                                                 | ✓ VERIFIED | `backend/app/config.py:109`.                                                                                                                                                                                                                                                                   |
| 6   | D-04/D-05: `Settings.amadeus_api_key: SecretStr \| None = None` and `amadeus_api_secret: SecretStr \| None = None`                                   | ✓ VERIFIED | `backend/app/config.py:110-111`.                                                                                                                                                                                                                                                               |
| 7   | T-07-02 / T-07-01 mitigations: `SecretStr` scrubs `__str__`, `Literal` rejects bogus env values                                                      | ✓ VERIFIED | `tests/unit/test_config.py` `test_amadeus_*` battery passes (10 amadeus-prefixed tests).                                                                                                                                                                                                       |
| 8   | D-12: Async-safe `call_with_breaker(breaker, coro_fn, *args, **kwargs)` exists using `state.before_call` / `_handle_error` / `_handle_success`       | ✓ VERIFIED | `backend/app/tools/circuit_breaker.py:84-96`.                                                                                                                                                                                                                                                  |
| 9   | D-12: Calling past `fail_max` consecutive system errors trips the circuit; subsequent calls raise `pybreaker.CircuitBreakerError`                    | ✓ VERIFIED | `tests/unit/test_circuit_breaker.py` (8 tests pass).                                                                                                                                                                                                                                           |
| 10  | `pybreaker>=1.4.1,<2.0` declared with rationale comment                                                                                              | ✓ VERIFIED | `backend/pyproject.toml:32`.                                                                                                                                                                                                                                                                   |
| 11  | `AmadeusFlightClient` is a concrete subclass of `FlightAPIClient` (ABC) implementing all four abstract methods                                       | ✓ VERIFIED | `amadeus_client.py:146` declares `class AmadeusFlightClient(FlightAPIClient)`; `health_check`, `search`, `get_flight_details`, `check_availability` all defined.                                                                                                                               |
| 12  | D-01: Token cache — concurrent `_get_token()` callers trigger exactly one underlying refresh under `asyncio.Lock`                                    | ✓ VERIFIED | `tests/unit/test_amadeus_token_cache.py::test_concurrent_callers_refresh_token_once` passes; double-checked locking at `amadeus_client.py:216-228`.                                                                                                                                            |
| 13  | D-02: OAuth2 client_credentials POST to `${base_url}/v1/security/oauth2/token`; no token persistence across restarts                                 | ✓ VERIFIED | `_TOKEN_PATH = "/v1/security/oauth2/token"` (line 161); `_refresh_token` uses `grant_type=client_credentials` form (lines 273-284); no on-disk cache.                                                                                                                                          |
| 14  | D-12: Composition order — `@retry_on_failure` wraps `_fetch_with_retry_breaker` outside, `call_with_breaker` inside, `_search_impl` (pyreqwest GET)  | ✓ VERIFIED | `amadeus_client.py:398` decorator on `_fetch_with_retry_breaker`; line 412 `call_with_breaker(self._breaker, self._search_impl, ...)`.                                                                                                                                                         |
| 15  | D-13: `pybreaker.CircuitBreakerError` mid-search mapped to `APIServerError(retryable=False)` so tenacity does NOT retry into open breaker            | ✓ VERIFIED | `amadeus_client.py:419-423`; `tests/unit/test_amadeus_client.py::test_circuit_breaker_open_raises_apiservererror_not_retried` passes.                                                                                                                                                          |
| 16  | D-11: HTTP status mapping in `_raise_from_http_status` — 429/5xx retryable=True; non-429 4xx retryable=False                                         | ✓ VERIFIED | `amadeus_client.py:109-143`; `tests/unit/test_amadeus_error_mapping.py::test_raise_from_http_status` parametrizes over 6 HTTP codes, all green.                                                                                                                                                |
| 17  | D-11: HTTP status mapping holds end-to-end — 401 surfaces as `APIClientError(retryable=False)`, not a generic retryable APIError                     | ✓ VERIFIED | **CR-02 closed.** `_refresh_token` (lines 269-313) now uses `error_for_status(True)` on the OAuth POST and adds explicit `except StatusError` (delegates to `_raise_from_http_status`), `except RequestTimeoutError`, `except ConnectError` branches BEFORE the catch-all. Locked at unit level by `tests/unit/test_amadeus_token_cache.py::test_refresh_token_401_raises_apiclient_error_not_retryable` AND at e2e level by the tightened `tests/e2e_amadeus/test_amadeus_client.py::test_error_mapping_401_with_bad_credentials` (asserts `APIClientError` + `retryable is False`, not the looser `APIError`). Malformed 2xx body now raises `APIError(retryable=False)` via the focused guard at lines 321-328 — locked by `test_refresh_token_malformed_body_raises_non_retryable`. |
| 18  | D-07/D-08/D-09: Vendor-neutral shape after normalization (multi-segment, layovers, price, IATA, ISO-8601, carriers, count, query); raw payload absent | ✓ VERIFIED | `_parse_flight_offers` (lines 503-566) constructs `Flight` directly; no raw vendor payload returned. `normalize_amadeus_offer` retains its Phase 4.6 vendor-neutral contract.                                                                                                                  |
| 19  | Naive datetimes from Amadeus get UTC attached before constructing `Flight` / `FlightEndpoint` (Pitfall 2)                                            | ✓ VERIFIED | `amadeus_client.py:537-540` explicit `tzinfo is None` guards in parser; `flight_search.py` `normalize_amadeus_offer` matches. `tests/unit/test_amadeus_client.py::test_naive_datetime_normalized_to_utc` passes.                                                                              |
| 20  | `pyreqwest>=0.12.0` declared in `pyproject.toml`                                                                                                     | ✓ VERIFIED | `backend/pyproject.toml:34`.                                                                                                                                                                                                                                                                   |
| 21  | D-04 / D-05: Lifespan branches on `amadeus_env` AND credential presence; `mock` env or missing creds → `MockFlightAPIClient` + `flight_provider='mock'`; missing creds in non-mock mode logs WARN with literal `"AMADEUS_* creds missing"` | ✓ VERIFIED | `backend/app/api/main.py:63-85`; `tests/integration/test_lifespan_flight_provider.py` covers all three branches.                                                                                                                                                                               |
| 22  | D-06: `GET /health` returns `{status, flight_provider}`; field ∈ {real, mock}                                                                        | ✓ VERIFIED | `backend/app/api/routes/routes.py:430-444`; `tests/integration/test_health.py` asserts new shape.                                                                                                                                                                                              |
| 23  | D-14: e2e_amadeus directory exists, default selectors don't run it, `pytestmark = skipif(not AMADEUS_AVAILABLE)`                                     | ✓ VERIFIED | `backend/tests/e2e_amadeus/{__init__.py, conftest.py, test_amadeus_client.py}` present; default `pytest tests/unit tests/integration` does not collect. Without env vars: 4 tests skipped (verified via `uv run pytest tests/e2e_amadeus/`).                                                  |
| 24  | D-14 / D-15: `just test-amadeus` exists; CI `amadeus-e2e` job gated on `vars.AMADEUS_E2E_ENABLED=='true'` AND `secrets.AMADEUS_API_*`; README documents credential setup | ✓ VERIFIED | `justfile:25-26`; `.github/workflows/ci.yml:121-164`; `README.md:85-90, 98-99, 109-124`.                                                                                                                                                                                                       |
| 25  | `AmadeusFlightClient.search` returns correct results for all valid offset values (pagination contract)                                               | ✓ VERIFIED | **CR-01 closed (Path A).** `_search_impl` now requests `params["max"] = str(limit + offset)` at `amadeus_client.py:465` (was `str(limit)`); the post-fetch slice `flights[offset : offset + limit]` at line 396 is preserved. Locked by `tests/unit/test_amadeus_client.py::test_search_offset_returns_correct_slice` which calls `search(limit=2, offset=2)` against a 4-flight stubbed `_search_impl` and asserts the slice returns `["F2", "F3"]` plus the `(query, limit=2, offset=2)` forwarding contract through `call_with_breaker`. |

**Score:** 25/25 truths verified.

### Required Artifacts

| Artifact                                                              | Expected                                                              | Status     | Details                                                  |
| --------------------------------------------------------------------- | --------------------------------------------------------------------- | ---------- | -------------------------------------------------------- |
| `backend/app/tools/retry.py`                                          | tenacity-backed `retry_on_failure`; preserves public signature        | ✓ VERIFIED | reraise=True; signature preserved                        |
| `backend/tests/unit/test_retry.py`                                    | 8 existing tests + reraise regression test                            | ✓ VERIFIED | All retry tests pass                                     |
| `backend/app/config.py`                                               | `amadeus_env` Literal + `amadeus_api_*` SecretStr fields              | ✓ VERIFIED | Lines 109-111                                            |
| `backend/tests/unit/test_config.py`                                   | tests for amadeus_* fields including SecretStr scrubbing              | ✓ VERIFIED | 10 amadeus-prefixed tests pass                           |
| `backend/app/tools/circuit_breaker.py`                                | async-safe `call_with_breaker`                                        | ✓ VERIFIED | uses `state.before_call` / `_handle_error` / `_handle_success` |
| `backend/tests/unit/test_circuit_breaker.py`                          | trip threshold + decorator anti-pattern + propagation tests           | ✓ VERIFIED | 8 tests pass                                             |
| `backend/app/flights/amadeus_client.py`                               | `AmadeusFlightClient(FlightAPIClient)` + token cache + composed search | ✓ VERIFIED | 638 lines; CR-01 + CR-02 both fixed at HEAD              |
| `backend/app/tools/flight_search.py`                                  | `normalize_amadeus_offer` with UTC-on-naive-datetime fix              | ✓ VERIFIED | UTC fallback present                                     |
| `backend/tests/unit/test_amadeus_client.py`                           | search composition + naive-datetime + offset-slice tests              | ✓ VERIFIED | 5 tests pass (was 4; +`test_search_offset_returns_correct_slice`) |
| `backend/tests/unit/test_amadeus_token_cache.py`                      | concurrent-refresh + proactive refresh + 401 + malformed-body         | ✓ VERIFIED | 5 tests pass (was 3; +`test_refresh_token_401_raises_apiclient_error_not_retryable`, +`test_refresh_token_malformed_body_raises_non_retryable`) |
| `backend/tests/unit/test_amadeus_error_mapping.py`                    | parametrized HTTP-status mapping test                                 | ✓ VERIFIED | 6 parametrized cases pass                                |
| `backend/app/api/main.py` lifespan                                    | auto-fallback branch + `app.state.flight_provider`                    | ✓ VERIFIED | WARN log line emitted                                    |
| `backend/app/api/routes/routes.py` `/health`                          | `flight_provider` field exposed                                       | ✓ VERIFIED | Lines 430-444                                            |
| `backend/tests/integration/test_health.py`                            | shape assertion + flight_provider field                                | ✓ VERIFIED | 2 tests pass                                             |
| `backend/tests/integration/test_lifespan_flight_provider.py`          | three branch tests (mock env, missing creds, real creds)              | ✓ VERIFIED | 3 tests pass                                             |
| `backend/tests/e2e_amadeus/{__init__.py, conftest.py, test_amadeus_client.py}` | gated live-API suite                                            | ✓ VERIFIED | 4 tests skipped without env vars; `test_error_mapping_401_with_bad_credentials` now asserts `APIClientError` + `retryable is False` (contract, not bug) |
| `justfile`                                                            | `test-amadeus` target                                                  | ✓ VERIFIED | Lines 25-26                                              |
| `.github/workflows/ci.yml`                                            | gated `amadeus-e2e` job                                                | ✓ VERIFIED | Lines 121-164                                            |
| `README.md`                                                           | AMADEUS_* credential setup section                                     | ✓ VERIFIED | Lines 85-90, 98-99, 109-124                              |

### Key Link Verification

| From                                                | To                                                  | Via                                              | Status   | Details                                                                |
| --------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------ | -------- | ---------------------------------------------------------------------- |
| `app/tools/retry.py`                                | `tenacity` (`stop_after_attempt`, `wait_exponential`, `retry_if_exception`) | `@retry` decorator factory with `reraise=True`   | ✓ WIRED  | retry.py:23, 73-78                                                     |
| `app/tools/circuit_breaker.py`                      | `pybreaker.CircuitBreaker.state`                    | `before_call` / `_handle_error` / `_handle_success` | ✓ WIRED  | circuit_breaker.py:84-95                                                |
| `app/flights/amadeus_client.py` `_refresh_token`    | `app.flights.amadeus_client._raise_from_http_status` | `except StatusError` branch (line 286-292)      | ✓ WIRED  | NEW: closes CR-02. Mirrors `_search_impl` instrumentation.             |
| `app/flights/amadeus_client.py` `_fetch_with_retry_breaker` | `app.tools.retry.retry_on_failure`        | `@retry_on_failure(max_retries=3, backoff_base=2.0)` | ✓ WIRED | amadeus_client.py:398                                                  |
| `app/flights/amadeus_client.py` `_fetch_with_retry_breaker` | `app.tools.circuit_breaker.call_with_breaker` | direct call, forwards `(query, limit, offset)` positionally | ✓ WIRED | amadeus_client.py:412-418                                              |
| `app/flights/amadeus_client.py` `_search_impl`      | `pyreqwest.client.ClientBuilder`                    | async context manager + `error_for_status(True)` + `get().bearer_auth().query()` | ✓ WIRED  | amadeus_client.py:469-478                                              |
| `app/flights/amadeus_client.py` `_refresh_token`    | `pyreqwest.client.ClientBuilder`                    | async context manager + `error_for_status(True)` + `post().form()` | ✓ WIRED  | amadeus_client.py:269-284 — `error_for_status(True)` is what makes the 401 surface as StatusError instead of being parsed as JSON. |
| `app/api/main.py` lifespan                          | `app.flights.amadeus_client.AmadeusFlightClient`    | conditional construction + `app.state.flight_client` | ✓ WIRED  | main.py:80-85, 115                                                     |
| `app/api/routes/routes.py` `/health`                | `app.state.flight_provider`                         | `request.app.state` read                         | ✓ WIRED  | routes.py:443                                                          |
| `tests/e2e_amadeus/conftest.py`                     | `app.flights.amadeus_client.AmadeusFlightClient`    | `amadeus_client` module-scoped fixture          | ✓ WIRED  | conftest.py + test_amadeus_client.py confirm import + use              |
| `.github/workflows/ci.yml`                          | `secrets.AMADEUS_API_KEY` / `secrets.AMADEUS_API_SECRET` | `env:` block on `amadeus-e2e` job               | ✓ WIRED  | ci.yml:137-138                                                          |
| `justfile`                                          | `tests/e2e_amadeus/`                                | `test-amadeus` target                            | ✓ WIRED  | justfile:25-26                                                          |

### Behavioral Spot-Checks

| Behavior                                                                    | Command                                                                                                | Result                                | Status   |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------- | -------- |
| Amadeus unit tests green (token cache + error mapping + client composition + new CR-01/CR-02 regression locks) | `cd backend && uv run pytest tests/unit/test_amadeus_*.py -v`                                          | 16 passed (was 13; +3 new)            | ✓ PASS   |
| Default unit + non-DB integration suite green                               | `cd backend && uv run pytest tests/unit/ tests/integration/ --ignore=tests/integration/db -q`         | 358 passed, 4 skipped (was 355; +3 new) | ✓ PASS   |
| e2e_amadeus tests skipped without credentials                               | `cd backend && uv run pytest tests/e2e_amadeus/ -q`                                                    | 4 skipped                             | ✓ PASS   |
| CR-01 fix at HEAD: `params["max"] = str(limit + offset)`                    | `grep -n '"max"' backend/app/flights/amadeus_client.py`                                                | Line 465 returns `"max": str(limit + offset)` | ✓ PASS   |
| CR-02 fix at HEAD: `error_for_status(True)` + StatusError branch in `_refresh_token` | `sed -n '269,313p' backend/app/flights/amadeus_client.py`                                       | `error_for_status(True)` + 4 explicit branches present, malformed-body guard at 321-328 | ✓ PASS   |
| Live Amadeus token + search                                                 | `AMADEUS_API_KEY=... AMADEUS_API_SECRET=... just test-amadeus`                                        | not runnable (no creds in env)        | ? SKIP   |

### Requirements Coverage

| Requirement         | Source Plan                                          | Description (from REQUIREMENTS.md)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Status        | Evidence                                                                                                                                                                                              |
| ------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| REQ-real-flight-api | 07-01, 07-02, 07-03, 07-04, 07-05, 07-06, 07-07      | Replace MockFlightAPIClient with a real flight provider client (Amadeus) behind FlightAPIClient ABC. Real client uses pyreqwest. Existing retry decorator + APIError hierarchy reused. Vendor-neutral JSON shape from Phase 4.6 is canonical. Mock client remains test default via DI override. Real-API integration tests gated on AMADEUS_* secrets in E2E job; PR CI does not require API keys. Documentation describes credential setup for local + CI use. | ✓ SATISFIED   | All structural pieces in place AND the two correctness defects (CR-01 offset double-application, CR-02 token-refresh status mishandling) are now closed at HEAD with regression locks at the unit and e2e levels. The `search` and `_get_token` paths now honor the documented contracts. |

No orphaned requirements: REQUIREMENTS.md maps `REQ-real-flight-api` to Phase 7 only and every plan in this phase declared it.

### Anti-Patterns Found

| File                                          | Line       | Pattern                                                                                              | Severity   | Impact                                                                                                                                                                       |
| --------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/app/flights/amadeus_client.py`       | 503-566    | `_parse_flight_offers` raises `KeyError`/`IndexError` on malformed offers (WR-05)                     | ⚠️ WARNING | Single bad offer crashes whole search; raw exception escapes into `call_with_breaker` and counts toward fail_max. Pre-existing; explicitly deferred per CONTEXT boundaries.  |
| `backend/app/flights/amadeus_client.py`       | 221-228    | Token cache slow-path holds lock across network call (WR-04)                                          | ⚠️ WARNING | Failure storm under cancellation. Pre-existing; deferred. CR-02 is now fixed so this is no longer compounded.                                                                |
| `backend/app/tools/flight_search.py`          | 399-400    | `max_price <= 0` rejection inconsistent with peers; error message "positive number" (WR-02)           | ⚠️ WARNING | Inconsistent with peer validators. Pre-existing; deferred.                                                                                                                   |
| `backend/app/tools/flight_search.py`          | 49-64      | `_extract_carrier_iata` silent fallback to `"ZZ"` without log (WR-03)                                 | ⚠️ WARNING | Diagnostic signal lost; downstream UI shows misleading code. Pre-existing; deferred.                                                                                         |
| `backend/app/tools/flight_search.py`          | 428-429    | Broad `except Exception: return f"...{e}"` returns raw `str(e)` to LLM (WR-06)                        | ⚠️ WARNING | Information disclosure path bypasses T-07-02 message-shape discipline. Pre-existing; deferred.                                                                                |
| `backend/app/api/routes/routes.py`            | 109-110, 201-202, 211, 383-388, 414-415 | Routes reach into `chat_service._metadata` (WR-01)                                                    | ℹ️ INFO    | Pre-existing; not introduced by this phase.                                                                                                                                  |
| `backend/tests/unit/test_retry.py`            | 18-32, 45-49 | `failing_function.attempts` shared module-level mutable counter (WR-07)                            | ℹ️ INFO    | Test isolation hazard; not blocking.                                                                                                                                         |
| `backend/pyproject.toml`                      | 13         | Runtime `httpx>=0.27.0` despite ADR-008 ban (IN-01)                                                   | ℹ️ INFO    | Pre-existing; out of scope for goal-backward verification.                                                                                                                   |
| `backend/app/flights/amadeus_client.py`       | 63-78      | `_iso_pt_to_minutes` silent 0-return on unparseable durations (IN-04)                                 | ℹ️ INFO    | Silent zero flows into duration filter. Low priority.                                                                                                                        |
| Pre-existing `ruff format` drift (5 files)    | various    | `just check` fails on `ruff format --check` for files with pre-existing format drift (logged in `deferred-items.md`) | ℹ️ INFO    | Confirmed pre-existing on baseline `18a9096`; `ruff check` (lint) and `mypy` both pass cleanly. Out of scope for gap closure. Recommended: `chore(*): apply ruff format` plan. |

**No `TBD` / `FIXME` / `XXX` debt markers found in any modified files** (verified via `grep -nE "TBD|FIXME|XXX"` on all four files touched by Plan 07-07: `amadeus_client.py`, `test_amadeus_client.py`, `test_amadeus_token_cache.py`, `e2e_amadeus/test_amadeus_client.py`). Debt-marker gate clear.

### Human Verification Required

Same four items as the prior verification — none can be exercised without live Amadeus sandbox credentials or a running FastAPI process. They are NOT regressions from Plan 07-07; they are inherent to the live-credential boundary documented in CONTEXT.md and 07-DISCUSSION-LOG.md.

1. **Real Amadeus sandbox token fetch + search end-to-end**
   - Test: With `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` set, run `just test-amadeus`.
   - Expected: All four e2e_amadeus tests pass against the live sandbox: token fetched, MAD→BCN search returns ≥1 result, vendor-neutral fields populated, bad-credentials path now raises `APIClientError` + `retryable is False` (newly tightened by Plan 07-07).
   - Why human: Requires real Amadeus sandbox credentials and live HTTPS; out of scope for grep-based verification.

2. **`/health` surfaces `flight_provider='real'` under real credentials**
   - Test: With creds set, `curl http://localhost:8000/health`.
   - Expected: `{"status":"healthy","flight_provider":"real"}`.
   - Why human: Requires running the FastAPI app with live credentials.

3. **WARN log line emits exactly when AMADEUS_ENV is non-mock and creds are missing**
   - Test: Boot the backend with `AMADEUS_ENV=test` and no `AMADEUS_API_KEY` / `AMADEUS_API_SECRET`.
   - Expected: Exactly one WARN log line containing the substring `AMADEUS_* creds missing`.
   - Why human: Log routing in production environments is configurable; the test only verifies the logger emit, not the deployed sink.

4. **Pitfall 1 — sandbox sparse routes**
   - Test: Run `test_real_search_returns_results` with live keys.
   - Expected: MAD→BCN returns ≥1 offer.
   - Why human: Sandbox content is operationally variable; fall-back to LON→NYC if zero offers.

### Closure Summary

The phase goal is structurally and behaviorally achieved. Plan 07-07 closed both BLOCKERS without introducing regressions:

- **CR-01 (pagination):** Path A applied at `amadeus_client.py:465` — `params["max"] = str(limit + offset)`. The post-fetch slice in `search()` is preserved at line 396. Locked by `test_search_offset_returns_correct_slice` which proves both the slice content (`["F2", "F3"]`) and the forwarding contract through `call_with_breaker`.
- **CR-02 (token refresh):** `_refresh_token` (lines 230-331) now uses `error_for_status(True)` + four explicit `except` branches BEFORE the catch-all (StatusError → `_raise_from_http_status`; RequestTimeoutError → `APITimeoutError(retryable=True)`; ConnectError → `APITimeoutError(retryable=True)`; catch-all retained as defense-in-depth). A focused malformed-body guard at lines 321-328 maps a 2xx response missing `access_token`/`expires_in` onto `APIError(retryable=False)`. T-07-02 / T-07-03 message-scrubbing discipline preserved (no `str(exc)` echoed). Locked at the unit level by `test_refresh_token_401_raises_apiclient_error_not_retryable` and `test_refresh_token_malformed_body_raises_non_retryable`, and at the e2e level by the tightened `test_error_mapping_401_with_bad_credentials` (`APIClientError` + `retryable is False`).

Test counts confirm zero regressions: default suite 355 → 358 passed (+3 new regression locks), 4 skipped unchanged. e2e_amadeus suite still gated correctly (4 skipped without creds).

The seven warning-level findings (WR-01 through WR-07) and five info findings (IN-01 through IN-05) from `07-REVIEW.md` plus the pre-existing `ruff format` drift are explicitly deferred per Plan 07-07's CONTEXT scope. None are must-haves for `REQ-real-flight-api`.

**Status: human_needed** — all 25 truths VERIFIED at the codebase level; the four live-sandbox / running-app checks remain outstanding by design (they require credentials and a deployed instance).

---

_Re-verified: 2026-06-05 (supersedes prior `gaps_found` report at 23/25)_
_Verifier: Claude (gsd-verifier)_
