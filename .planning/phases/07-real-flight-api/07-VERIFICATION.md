---
phase: 07-real-flight-api
verified: 2026-06-06T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `just test-duffel` with a real DUFFEL_API_TOKEN against the Duffel sandbox"
    expected: "All four e2e_duffel tests (test_auth_probe, test_real_search_returns_results, test_vendor_neutral_shape, test_error_mapping_401_with_bogus_token) pass live; MAD→BCN search returns ≥1 offer (Pitfall 1 fallback to LON→NYC if sandbox sparse)"
    why_human: "Live API verification requires a Duffel sandbox token; the executor never had one (07-04 SUMMARY confirms 'Live Test Results: Not exercised'). Static collection-skip is verified, but real-network behaviour remains untested."
  - test: "Verify Duffel-specific tokens are redacted in real log output"
    expected: "Generating a log line containing a duffel_test_<20+chars> or duffel_live_<20+chars> token through the application logger surfaces 'duffel_[REDACTED]' rather than the live token"
    why_human: "Unit tests cover _scrub() in isolation, but the in-process logging filter wiring depends on uvicorn handler ordering at runtime. A live smoke check confirms the install_log_scrubber() seam holds end-to-end."
  - test: "Verify CI duffel-e2e job actually runs when an admin sets vars.DUFFEL_E2E_ENABLED=true and secrets.DUFFEL_API_TOKEN"
    expected: "Job becomes active on next push, runs the four-test suite live, all tests pass; PR CI from forks remains unaffected"
    why_human: "Cannot programmatically verify GitHub Actions secrets/vars wiring without admin access; YAML structure verification only proves the gate is shaped correctly, not that GitHub will accept the gate at scheduling time."
---

# Phase 7: real-flight-api Verification Report

**Phase Goal:** The agent calls a real flight provider (Duffel) through the existing `FlightAPIClient` ABC, with `pyreqwest` for outbound HTTP, retry + circuit breaker, and clean error mapping; the mock remains the test default.

**Verified:** 2026-06-06T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status     | Evidence |
| --- | ----- | ---------- | -------- |
| 1   | A Duffel client implements `FlightAPIClient`, uses `pyreqwest` for async I/O (not aiohttp/httpx), reuses retry decorator + circuit breaker + `APIError` hierarchy. | ✓ VERIFIED | `backend/app/flights/duffel_client.py:173` declares `class DuffelFlightClient(FlightAPIClient):`. Imports include `pyreqwest.client.ClientBuilder`, `pybreaker.CircuitBreaker`, `app.tools.retry.retry_on_failure`, `app.tools.circuit_breaker.call_with_breaker`, and `app.exceptions.{APIClientError, APIRateLimitError, APIServerError, APITimeoutError}`. `grep -cE '^(import\|from) (aiohttp\|httpx\|requests\|urllib3)' backend/app/flights/duffel_client.py` returns **0** — ADR-008 holds. Composition `@retry_on_failure(max_retries=3, backoff_base=2.0)` (line 403) wraps `_fetch_with_retry_breaker`, which calls `call_with_breaker(self._breaker, self._search_impl, ...)` (line 414). `pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60, throw_new_error_on_trip=True)` at line 207. |
| 2   | With a real Duffel API token configured, `search_flights` returns live results in the vendor-neutral JSON contract from Phase 4.6; without the token, the system falls back to the mock client. | ✓ VERIFIED (static) / ⚠️ Live path needs human | `backend/app/api/main.py:63-77` — lifespan branch: when `duffel_env != "mock"` AND `duffel_api_token` is non-empty, constructs `DuffelFlightClient(api_token=duffel_token_value, base_url="https://api.duffel.com")` and sets `flight_provider = "real"`. Otherwise, `MockFlightAPIClient(seed=42)` and `flight_provider = "mock"`. `_normalize_offer` (line 308) maps onto vendor-neutral `Flight` model. Integration test `test_lifespan_constructs_duffel_client_with_real_token` passes. **Live verification deferred to human (no DUFFEL_API_TOKEN available to executor).** Boot smoke `cd backend && env -u DUFFEL_API_TOKEN uv run python -c "from app.api.main import app; print('boot ok')"` exits 0 (Pitfall 6 fallback works). |
| 3   | Real-API integration tests exist and are gated on the Duffel API token being present in the E2E job; PR CI does not require API keys. | ✓ VERIFIED | `backend/tests/e2e_duffel/test_duffel_client.py:35` declares `pytestmark = pytest.mark.skipif(not DUFFEL_AVAILABLE, reason="DUFFEL_API_TOKEN not set")`. Four tests present: `test_auth_probe`, `test_real_search_returns_results`, `test_vendor_neutral_shape`, `test_error_mapping_401_with_bogus_token`. With `DUFFEL_API_TOKEN` unset: 4 skipped at collection. `.github/workflows/ci.yml` `duffel-e2e` job has `if: vars.DUFFEL_E2E_ENABLED == 'true'` at job level + `env: DUFFEL_API_TOKEN: ${{ secrets.DUFFEL_API_TOKEN }}` on the pytest step. PR CI from forks never receives the secret. |
| 4   | Default `pytest` continues to pass with the mock client as the DI default; documentation describes credential setup for local and CI use. | ✓ VERIFIED | `cd backend && env -u DUFFEL_API_TOKEN uv run pytest tests/unit/ tests/integration/ tests/e2e_duffel/ --ignore=tests/integration/db -q` → **363 passed, 8 skipped in 14.01s** (4 skips are e2e_duffel collection-time skips; rest are pre-existing). README §"Duffel Flight API (Phase 7)" at line 73 documents signup → local config → CI admin config → Pitfall 1. `.env.example` has `DUFFEL_API_TOKEN=` placeholder + commented `# DUFFEL_ENV=test` row. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/flights/duffel_client.py` | DuffelFlightClient (FlightAPIClient impl) + helpers | ✓ VERIFIED | 484 lines, 0 forbidden HTTP lib imports, includes `_DUFFEL_VERSION='v2'`, `_raise_from_http_status`, `_iso_pt_to_minutes`, `_apply_filters`, `_sort_flights`, `_status_from_details`, `_auth_probe`, `_build_offer_request_body`, `_normalize_offer`, `_search_impl`, `_fetch_with_retry_breaker`, `search`. Wired by `app/api/main.py:22, 73`. |
| `backend/app/api/main.py` | Lifespan auto-fallback (D-02) | ✓ VERIFIED | Lines 63-77 implement the branch; line 69 has the WARN literal `"DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient"`. |
| `backend/app/config.py` | duffel_api_token + duffel_env Settings fields | ✓ VERIFIED | Lines 74-75: `duffel_api_token: SecretStr \| None = None` + `duffel_env: Literal["test", "live", "mock"] = "test"`. |
| `backend/app/llm/log_scrubbing.py` | Duffel bearer token regex in SECRET_PATTERNS | ✓ VERIFIED | Line 48: `(re.compile(r"duffel_(?:test\|live)_[A-Za-z0-9_-]{20,}"), "duffel_[REDACTED]")`. Non-capturing group per IN-07 fix. |
| `backend/app/tools/flight_search.py` | Cleaned tool entry-point (D-08) | ✓ VERIFIED | `grep -cE 'def normalize_amadeus_offer\|def normalize_skyscanner_itinerary'` returns 0. Vendor-neutral `search_flights`, `_to_flight_search_result`, `_extract_carrier_iata`, `_to_iso_duration` preserved. |
| `backend/tests/unit/test_duffel_client.py` | Unit coverage for client | ✓ VERIFIED | 11 tests, all green in current run. |
| `backend/tests/unit/test_duffel_error_mapping.py` | D-04 mapping table | ✓ VERIFIED | 8 parametrised rows, all green. |
| `backend/tests/unit/test_config_duffel.py` | Settings.duffel_* contract | ✓ VERIFIED | 5 tests, all green. |
| `backend/tests/unit/llm/test_log_scrubbing.py` | Extended scrubber coverage | ✓ VERIFIED | 33 tests pass (including 5 new Duffel cases). |
| `backend/tests/integration/test_lifespan_flight_provider.py` | 3 lifespan branch tests | ✓ VERIFIED | `test_lifespan_uses_mock_when_duffel_env_is_mock`, `test_lifespan_falls_back_to_mock_when_token_missing`, `test_lifespan_constructs_duffel_client_with_real_token` all green. |
| `backend/tests/e2e_duffel/{__init__,conftest,test_duffel_client}.py` | Gated suite (D-12) | ✓ VERIFIED (static) | Module-level pytestmark skipif; 4 tests; conftest exposes module-scoped `duffel_client` fixture. With token unset: 4 skipped at collection. |
| `backend/tests/fixtures/duffel/{oneway,roundtrip}.json` | Recorded offer payloads | ✓ VERIFIED | Both fixtures present, hand-crafted per RESEARCH §"Code Examples 3", under 5 KB each, no token leakage. |
| `justfile` | test-duffel target | ✓ VERIFIED | Line 33: `test-duffel:` target with body `cd backend && uv run pytest tests/e2e_duffel/ -v`. |
| `.github/workflows/ci.yml` | duffel-e2e gated job | ✓ VERIFIED | Job present; `if: vars.DUFFEL_E2E_ENABLED == 'true'` at job level; `DUFFEL_API_TOKEN: ${{ secrets.DUFFEL_API_TOKEN }}` on pytest step. |
| `README.md` | Duffel credential setup section | ✓ VERIFIED | §"Duffel Flight API (Phase 7)" at line 73; covers signup, local config, `just test-duffel`, CI admin config, Pitfall 1. `grep -cE 'DUFFEL_API_TOKEN' README.md` returns 6. |
| `.env.example` | DUFFEL_API_TOKEN + DUFFEL_ENV documented | ✓ VERIFIED | `grep -cE '^DUFFEL_API_TOKEN=\|^# DUFFEL_ENV='` returns 2. Phase 7 / D-01 header block present. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `lifespan` (main.py) | `DuffelFlightClient` | Settings-driven branch | ✓ WIRED | `from app.flights.duffel_client import DuffelFlightClient` (line 22); branch at line 73 constructs the client when `duffel_env != "mock"` AND token non-empty. |
| `lifespan` | `app.state.flight_client` + `flight_provider` | DI seam | ✓ WIRED | Lines 106-107 set both attributes; `/health` reads `flight_provider` via `getattr(request.app.state, "flight_provider", "mock")` at `routes.py:443`. |
| `DuffelFlightClient.search` | `_fetch_with_retry_breaker → call_with_breaker → _search_impl` | retry/breaker composition | ✓ WIRED | Lines 403, 414, 456 wire the chain; open-breaker mapped to `APIServerError(retryable=False)` at line 415-419. Locked by `test_circuit_breaker_open_raises_apiservererror_not_retried`. |
| `_search_impl` | Duffel POST `/air/offer_requests` | pyreqwest builder | ✓ WIRED | Line 367-378: `ClientBuilder().timeout(...).error_for_status(True).build()` async-ctx; `client.post(url).query({"return_offers": "true"}).bearer_auth(self._api_token.get_secret_value()).header("Duffel-Version", _DUFFEL_VERSION).header("Accept", "application/json").body_json(body).build().send()`. |
| `_normalize_offer` | `Flight` model | field-by-field with UTC attach | ✓ WIRED | Lines 308-354; D-09 naive→UTC at lines 329-332; D-10 cabin path read at line 334. |
| `e2e_duffel` test module | `DUFFEL_API_TOKEN` env var | module-level pytestmark.skipif | ✓ WIRED | `pytestmark = pytest.mark.skipif(not DUFFEL_AVAILABLE, ...)` at test_duffel_client.py:35 (collection-time gate verified by skip output). |
| `duffel-e2e` CI job | `secrets.DUFFEL_API_TOKEN` + `vars.DUFFEL_E2E_ENABLED` | GitHub Actions if + env block | ✓ WIRED | YAML inspected: job-level `if`; step-level env. PR CI from forks never receives the secret. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `DuffelFlightClient.search` | `flights: list[Flight]` | `_fetch_with_retry_breaker` → `_search_impl` → live Duffel POST | Yes (live API; verified by static path; live execution requires human DUFFEL_API_TOKEN) | ⚠️ STATIC verified, FLOWING needs human |
| `app.state.flight_client` | flight_client | lifespan branch | Yes (constructs Duffel or Mock based on Settings) | ✓ FLOWING |
| `/health` `flight_provider` field | `app.state.flight_provider` | lifespan-set string `"real"`/`"mock"` | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Boot succeeds without Duffel token (Pitfall 6) | `cd backend && env -u DUFFEL_API_TOKEN uv run python -c "from app.api.main import app; print('boot ok')"` | exit 0, prints `boot ok` | ✓ PASS |
| Default test suite green with mock as default | `cd backend && env -u DUFFEL_API_TOKEN uv run pytest tests/unit/ tests/integration/ tests/e2e_duffel/ --ignore=tests/integration/db -q` | 363 passed, 8 skipped | ✓ PASS |
| e2e_duffel suite skips when token unset | `cd backend && env -u DUFFEL_API_TOKEN uv run pytest tests/e2e_duffel/ -v` | 4 skipped, 0 failed | ✓ PASS |
| ADR-008 forbidden HTTP libs absent from Duffel client | `grep -cE '^(import\|from) (aiohttp\|httpx\|requests\|urllib3)' backend/app/flights/duffel_client.py` | 0 | ✓ PASS |
| Live e2e_duffel against real Duffel sandbox | `just test-duffel` with DUFFEL_API_TOKEN set | not executed | ? SKIP (deferred to human) |

### Probe Execution

No probes are declared in PLAN frontmatter or `scripts/*/tests/probe-*.sh`; phase 7 uses pytest as its verification driver, which has been executed above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| REQ-real-flight-api | 07-01, 07-02, 07-03, 07-04 PLANs | Replace `MockFlightAPIClient` with a real Duffel client behind `FlightAPIClient` ABC; `pyreqwest` for HTTP; reuse retry/breaker/`APIError`; vendor-neutral JSON shape; mock remains test default; integration tests gated on token; documentation for local + CI. | ✓ SATISFIED (static) / ⚠️ Live path needs human | All four success criteria verified (truths #1-#4 above). Live behaviour against real Duffel sandbox is intentionally deferred to a human gate (see `human_verification`). |

No orphan requirements identified — `REQ-real-flight-api` is the sole declared requirement and is claimed across all four sub-plans.

### Anti-Patterns Found

Files modified in this phase scanned for stubs, debt markers, and hardcoded empty data. Findings:

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `backend/app/flights/duffel_client.py` | 461-471, 473-483 | `raise NotImplementedError` for `get_flight_details` and `check_availability` | ℹ️ Info | Documented v1 limitation per CONTEXT.md (only single-round-trip search is in scope); not invoked from `search_flights` tool path. Not a stub — explicit out-of-scope marker with docstring rationale. |
| (None) | — | TBD/FIXME/XXX debt markers | — | None found in phase-7-modified files. |

No blockers. The `NotImplementedError` methods are documented v1 limitations and never appear on the active call path.

### Human Verification Required

Three items require human testing — see frontmatter `human_verification` for full machine-readable form.

#### 1. Live Duffel sandbox e2e suite

**Test:** Run `just test-duffel` with a real `DUFFEL_API_TOKEN` against the Duffel sandbox.
**Expected:** All four e2e_duffel tests pass live; MAD→BCN 30-day-out search returns ≥1 offer (Pitfall 1: switch to LON→NYC manually if sandbox sparse for the chosen route).
**Why human:** The executor never had a Duffel sandbox token (07-04-SUMMARY explicitly: "Live Test Results: Not exercised. No DUFFEL_API_TOKEN was provided to the executor"). Static collection-skip and offline fixture-driven coverage are verified, but the real-network code path remains unrun.

#### 2. End-to-end log scrubber wiring at runtime

**Test:** Generate a log line containing a synthetic `duffel_test_xxxxxxxxxxxxxxxxxxxx` token through the running application and inspect the formatter output.
**Expected:** The token shape is replaced with `duffel_[REDACTED]` before reaching stdout/uvicorn access logs.
**Why human:** `_scrub()` is unit-tested in isolation; the install_log_scrubber → handler ordering chain depends on uvicorn + Python logging runtime state that grep cannot model.

#### 3. CI duffel-e2e activation by repo admin

**Test:** Set `vars.DUFFEL_E2E_ENABLED=true` and `secrets.DUFFEL_API_TOKEN=duffel_test_<real>` in GitHub repo settings; push a commit.
**Expected:** `duffel-e2e` job triggers, runs four tests live, all pass; PR CI from external contributors remains unaffected (no secret leakage).
**Why human:** Cannot programmatically verify GitHub Actions secrets/vars wiring without admin access to the repo Settings page.

### Gaps Summary

No blocking gaps were identified. All four ROADMAP success criteria are satisfied at the static-codebase level; the only items deferred are intentional live-API verifications that the executor had no credential to perform. The 07-REVIEW.md self-resolution log shows the WR-01..WR-05 + IN-01/02/03/04/07 findings were addressed in commits 824f3ea and a0e0b11; deferred IN-05/06/08/09 items are design choices, documented v1 limitations, or out-of-phase scope per the review.

---

_Verified: 2026-06-06T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
