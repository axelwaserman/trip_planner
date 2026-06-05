---
phase: 07-real-flight-api
plan: 05
subsystem: api
tags: [fastapi, lifespan, amadeus, health-check, dependency-injection, secret-management]

# Dependency graph
requires:
  - phase: 07-real-flight-api
    provides: "AmadeusFlightClient (Plan 04), Settings.amadeus_env + amadeus_api_key/secret SecretStr fields (Plan 02), retry/circuit-breaker wrappers (Plans 01/03)"
provides:
  - "Lifespan auto-fallback wiring: amadeus_env=='mock' OR missing creds → MockFlightAPIClient + flight_provider='mock' (with WARN log on the missing-creds branch); real creds → AmadeusFlightClient against env-appropriate base_url + flight_provider='real'"
  - "app.state.flight_client + app.state.flight_provider stashed before yield so routes (and Plan 06's e2e_amadeus tests) can observe the constructed implementation directly"
  - "GET /health extended with flight_provider field ('real'|'mock') so the choice is visible from outside the process"
  - "Locked WARN substring 'AMADEUS_* creds missing' for Plan 06 CI inspection"
affects: [07-06, future-phases-with-paid-flight-providers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Auto-fallback dependency injection: lifespan branches on env + credential presence and degrades gracefully when secrets are absent (no startup failure, observable WARN log)."
    - "Field-membership /health assertion: tests assert {status, flight_provider in {real, mock}} rather than exact-equality so the public-access invariant survives future shape additions."

key-files:
  created:
    - "backend/tests/integration/test_lifespan_flight_provider.py"
  modified:
    - "backend/app/api/main.py"
    - "backend/app/api/routes/routes.py"
    - "backend/tests/integration/test_health.py"
    - "backend/tests/integration/test_auth_routes.py"

key-decisions:
  - "Stash app.state.flight_client (the constructed implementation) alongside app.state.flight_provider, so tests can assert the concrete class directly without reaching into ChatService private attributes (._flight_client). This widens the lifespan's <truths> contract beyond the original PLAN.md but matches the plan's own success_criteria wording ('app.state.flight_client and app.state.flight_provider are set after startup')."
  - "monkeypatch.setattr('app.config.settings.amadeus_env', ...) works without import-reload because Settings is not frozen (no ConfigDict(frozen=True)). All three lifespan-branch tests use this pattern; no importlib.reload of app.api.main was needed."
  - "Test test_auth_routes::test_health_check_is_public was loosened from exact-equality to membership-style assertions to keep the public-access invariant orthogonal to /health shape evolution (Plan 07-05 broke its old assertion; Rule 1 inline fix)."

patterns-established:
  - "Lifespan auto-fallback: branch on Settings.amadeus_env + cred presence; emit WARN with literal substring 'AMADEUS_* creds missing' on the missing-creds path; never fail startup."
  - "/health surfaces a coarse capability fingerprint (flight_provider) — accept-disposition for T-07-02 documented in plan threat register."

requirements-completed: [REQ-real-flight-api]

# Metrics
duration: 12min
completed: 2026-06-05
---

# Phase 07 Plan 05: Lifespan AmadeusFlightClient Wiring + /health flight_provider Summary

**Lifespan now branches on amadeus_env + credential presence (auto-fallback to MockFlightAPIClient with WARN log when creds are missing) and /health surfaces the active flight provider, making Plan 04's AmadeusFlightClient observable end-to-end.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-06-05T06:38:48Z
- **Tasks:** 2
- **Files modified:** 4 (1 created)

## Accomplishments

- Lifespan in `backend/app/api/main.py` now constructs the right `FlightAPIClient` based on `Settings.amadeus_env` and credential presence (D-04, D-05). The missing-creds path logs WARN `"AMADEUS_* creds missing — falling back to MockFlightAPIClient"` and degrades gracefully — startup never fails because of missing secrets.
- `app.state.flight_client` and `app.state.flight_provider` are populated before `yield`, so routes and Plan 06's e2e_amadeus suite can read either directly.
- `GET /health` now returns `{"status": "healthy", "flight_provider": "real" | "mock"}` (D-06).
- Five new/updated integration tests cover all three branches of the lifespan plus the /health field shape; full unit + integration suite (excluding DB tests that require a live Postgres) is green.

## Task Commits

1. **Task 1: Lifespan auto-fallback + /health flight_provider** — `4d9487d` (feat)
2. **Task 2: /health field-shape + lifespan-branch integration tests** — `ea222f3` (test)

## Files Created/Modified

- `backend/app/api/main.py` — lifespan branches on `settings.amadeus_env` + cred presence; stashes `app.state.flight_client` and `app.state.flight_provider`; imports `AmadeusFlightClient` and the `FlightAPIClient` ABC for type annotation.
- `backend/app/api/routes/routes.py` — `/health` accepts `Request`, reads `app.state.flight_provider` (with `getattr(..., "mock")` defensive default), and returns the new shape.
- `backend/tests/integration/test_health.py` — replaced exact-equality assertion with field-membership checks; added `test_health_flight_provider_is_mock_without_credentials`. Both tests now use `with TestClient(app) as client:` so the lifespan actually runs.
- `backend/tests/integration/test_lifespan_flight_provider.py` — three new tests: `test_lifespan_uses_mock_when_amadeus_env_is_mock`, `test_lifespan_falls_back_to_mock_when_credentials_missing` (asserts the literal `"AMADEUS_* creds missing"` substring appears in `caplog`), `test_lifespan_constructs_amadeus_client_with_real_credentials` (asserts `_base_url == "https://test.api.amadeus.com"`, T-07-01 lock).
- `backend/tests/integration/test_auth_routes.py` — `test_health_check_is_public` loosened from exact-equality to membership-style assertions (Rule 1 inline fix; the old assertion broke when /health gained `flight_provider`).

## Decisions Made

- **`app.state.flight_provider` placement:** placed immediately after `app.state.chat_service`, grouped logically with the flight-related state. The plan's `<output>` requirement explicitly asked for this placement note. `app.state.flight_client` is stashed on the same line block.
- **`monkeypatch.setattr` on `app.config.settings`:** Settings is not frozen, so attribute mutation through `monkeypatch.setattr("app.config.settings.amadeus_env", "mock")` works directly — no `importlib.reload(app.api.main)` was required. This is the cleaner of the two approaches discussed in the plan; recorded here for Plan 06's reference.
- **WARN line wording:** the literal substring `"AMADEUS_* creds missing"` is locked by `test_lifespan_falls_back_to_mock_when_credentials_missing` (and asserted via `caplog.records[*].message`). Plan 06's CI inspection can rely on this exact substring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Updated `test_auth_routes::test_health_check_is_public`**
- **Found during:** Task 2 (running the full integration suite as the plan's verification step requires).
- **Issue:** The pre-existing test used exact-equality assertion `assert response.json() == {"status": "healthy"}`, which broke directly because of this plan's /health shape change.
- **Fix:** Loosened to membership-style assertions: `assert data["status"] == "healthy"` and `assert data["flight_provider"] in ("real", "mock")`. The public-access invariant (no auth needed for /health) is preserved.
- **Files modified:** `backend/tests/integration/test_auth_routes.py`
- **Verification:** Full integration suite (`tests/integration --ignore=tests/integration/db`) green: 69 passed, 3 skipped.
- **Committed in:** `ea222f3` (bundled with Task 2's test work since the failure was caused by the same code change).

**2. [Rule 2 — Missing Critical] Stashed `app.state.flight_client` (in addition to `app.state.flight_provider`)**
- **Found during:** Task 2 (running the lifespan-branch tests; assertions on `app.state.chat_service.flight_client` failed because `ChatService` exposes the client only as the private `_flight_client`).
- **Issue:** Without `app.state.flight_client`, integration tests would have to reach into `ChatService._flight_client` to assert the constructed implementation — a violation of encapsulation, and one the plan's own `<truths>` block already anticipated by listing `app.state.flight_client` as set after startup.
- **Fix:** Added `app.state.flight_client = flight_client` next to `app.state.flight_provider = ...` in `backend/app/api/main.py`. The lifespan-branch tests assert `app.state.flight_client` directly.
- **Files modified:** `backend/app/api/main.py`
- **Verification:** All 5 new tests pass; mypy + ruff clean.
- **Committed in:** `ea222f3` (bundled with Task 2 since the `app.state` line and the test that depends on it land together).

---

**Total deviations:** 2 auto-fixed (1 bug from cross-cutting test, 1 missing-critical app.state attribute that the plan's own `<truths>` block listed). Impact: minimal — both fixes were essential for the plan's verification commands to pass and for Plan 06's e2e_amadeus tests to assert the constructed client.

## Issues Encountered

- **DB-dependent integration tests skipped:** `tests/integration/db/test_alembic_round_trip.py` requires a live Postgres at `127.0.0.1:5432`. Pre-existing infrastructure dependency, unrelated to this plan; ran the rest of the integration suite via `--ignore=tests/integration/db` per the GSD scope-boundary rule (out-of-scope failures are not auto-fixed).
- **No real HTTP traffic in lifespan tests:** the lifespan only constructs `AmadeusFlightClient`; no OAuth token is fetched until `_get_token()` is awaited. The test that constructs a real client with fake credentials never makes an outbound request — verified by no network errors and by inspecting the constructor signature.

## Threat Flags

None — no new network endpoints, auth paths, or trust-boundary changes beyond the threat register that the plan already documents (T-07-01 mitigated by `_base_url` test lock; T-07-02 accepted; T-07-03 accepted with WARN-line credential-leak test).

## Next Phase Readiness

- Plan 06 (e2e_amadeus suite + CI gating) can now rely on:
  - `app.state.flight_client` being an `AmadeusFlightClient` instance when `AMADEUS_*` env vars are present in CI.
  - The literal WARN substring `"AMADEUS_* creds missing"` being emitted on the missing-creds path.
  - `/health` returning `flight_provider="real"` when real creds are wired.
- No blockers.

## Self-Check: PASSED

- Files: `backend/app/api/main.py` (modified, ✓), `backend/app/api/routes/routes.py` (modified, ✓), `backend/tests/integration/test_health.py` (modified, ✓), `backend/tests/integration/test_lifespan_flight_provider.py` (created, ✓), `backend/tests/integration/test_auth_routes.py` (modified, ✓).
- Commits: `4d9487d` (✓ in `git log`), `ea222f3` (✓ in `git log`).
- Verification: `cd backend && uv run pytest tests/integration/test_health.py tests/integration/test_lifespan_flight_provider.py -v` → 5 passed; `cd backend && uv run mypy app/api/main.py app/api/routes/routes.py` → no issues; `cd backend && uv run ruff check app/api/main.py app/api/routes/routes.py tests/integration/test_health.py tests/integration/test_lifespan_flight_provider.py tests/integration/test_auth_routes.py` → clean; full unit + integration suite (ex-DB) green.

---
*Phase: 07-real-flight-api*
*Completed: 2026-06-05*
