---
phase: 07-real-flight-api
plan: 03
subsystem: lifespan + tool entry-point cleanup + integration tests
tags: [duffel, lifespan, health, cleanup, integration-tests, phase-7]
requirements: [REQ-real-flight-api]
dependency_graph:
  requires:
    - "backend/app/config.py::Settings.duffel_api_token + Settings.duffel_env (Plan 07-01)"
    - "backend/app/flights/duffel_client.py::DuffelFlightClient (Plan 07-02)"
    - "backend/app/api/main.py::lifespan (existing Mock-only branch — replaced)"
  provides:
    - "Lifespan auto-fallback branch (D-02) — DuffelFlightClient on creds, MockFlightAPIClient otherwise"
    - "/health flight_provider integration coverage for both branches"
    - "D-08 dead-code lock (regression-lock test prevents normalize_amadeus_offer / normalize_skyscanner_itinerary reintroduction)"
  affects:
    - "Plan 07-04 README quickstart (operator now sees flight_provider in /health)"
    - "Plan 07-05 e2e_duffel suite (consumes the same lifespan path under DUFFEL_API_TOKEN)"
tech_stack:
  added: []
  patterns:
    - "S4: SecretStr + lifespan auto-fallback for optional credentials (Pitfall 6)"
    - "S6: ABC-implementation pair behind FastAPI lifespan (FlightAPIClient seam)"
    - "Empty-SecretStr-as-no-token guard (Plan 07-01 SUMMARY note carry-over)"
key_files:
  created:
    - "backend/tests/integration/test_lifespan_flight_provider.py"
  modified:
    - "backend/app/api/main.py"
    - "backend/app/tools/flight_search.py"
    - "backend/tests/unit/test_tool_json_normalization.py"
    - "backend/tests/integration/test_health.py"
decisions:
  - "Treat both None and empty SecretStr('') as 'no token' so the empty DUFFEL_API_TOKEN= row in .env.example takes the fallback path uniformly."
  - "Unwrap SecretStr at exactly one call site (the lifespan branch) — the bearer token never re-enters logged context after that point (T-07-03-01)."
  - "Keep the regression-lock test in test_tool_json_normalization.py despite the literal grep-count ambiguity in the plan's acceptance criteria; the lock is more valuable than a clean grep count and is what the plan's threat-model T-07-03-05 requires."
metrics:
  duration_minutes: 18
  tasks_completed: 3
  tests_added: 4
  tests_removed: 6
  loc_removed: 345
  completed_date: "2026-06-06"
---

# Phase 7 Plan 3: Lifespan + Cleanup Summary

D-02 lifespan auto-fallback lands: a fresh checkout boots with `MockFlightAPIClient` and a single WARN log; setting `DUFFEL_API_TOKEN` swaps in the real `DuffelFlightClient` against `https://api.duffel.com` with no other code changes. `/health` now accurately reports the active branch, integration tests cover all three lifespan paths, and `flight_search.py` is materially smaller because the vendor-specific normalizers (Amadeus + Skyscanner) — which had no live caller after the Phase 7 vendor switch — are gone.

## What Shipped

### Final lifespan branch shape (backend/app/api/main.py)

```python
# Initialize flight client.
# D-02: lifespan auto-fallback. Boot must NEVER fail because of missing
# creds (Pitfall 6). flight_provider = "real" only when DuffelFlightClient
# is constructed. An empty SecretStr (from the empty DUFFEL_API_TOKEN= row
# in .env.example — see Plan 07-01 SUMMARY notes) is treated as "no token"
# so the fallback path runs uniformly for both None and SecretStr('').
duffel_token = settings.duffel_api_token
duffel_token_value = duffel_token.get_secret_value() if duffel_token is not None else ""
if settings.duffel_env == "mock" or not duffel_token_value:
    if settings.duffel_env != "mock":
        # Pitfall 6 / T-07-02: WARN but do not raise. The literal log line
        # below is asserted by tests/integration/test_lifespan_flight_provider.py.
        logger.warning("DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient")
    flight_client: FlightAPIClient = MockFlightAPIClient(seed=42)
    flight_provider = "mock"
else:
    flight_client = DuffelFlightClient(
        api_token=duffel_token_value,
        base_url="https://api.duffel.com",
    )
    flight_provider = "real"
```

### LOC delta for `backend/app/tools/flight_search.py`

| Before | After | Delta |
|--------|-------|-------|
| 429 LOC | 266 LOC | **−163 LOC** |

`normalize_amadeus_offer` (~78 LOC) and `normalize_skyscanner_itinerary` (~82 LOC) were removed wholesale. Vendor-neutral helpers preserved: `_extract_carrier_iata`, `_to_iso_duration`, `_to_flight_search_result`, `search_flights`. Imports trimmed: `from datetime import UTC`, `from datetime import datetime`, `from typing import Any` — all unused after the deletion.

### Test count delta for `backend/tests/unit/test_tool_json_normalization.py`

| Tests before | Tests after | Delta |
|--------------|-------------|-------|
| 12 | 7 | **−6 deleted, +1 regression-lock added** |

LOC: 383 → 201 (−182). Deleted: `test_amadeus_offer_normalizes_without_lossy_collapse`, `test_amadeus_offer_carrier_name_comes_from_dictionaries`, `test_skyscanner_itinerary_normalizes_without_lossy_collapse`, `test_skyscanner_price_decimal_precision`, `test_skyscanner_empty_legs_raises`, `test_skyscanner_empty_segments_raises`. Added: `test_flight_search_module_no_amadeus_normalizers` (regression-lock per T-07-03-05). Module docstring updated to explain the D-08 deletion lineage.

### WARN log literal substring + em-dash codepoint

The lifespan emits exactly one WARN line when `duffel_env != "mock"` and the token is absent:

```
DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient
```

The em-dash is **U+2014** (verified `hex(ord('—')) == 0x2014`). `grep -F 'DUFFEL_API_TOKEN missing' backend/app/api/main.py | wc -l` returns **1** (single match — the comment was reworded to avoid a duplicate hit, see Deviations below).

### Boot smoke test (Pitfall 6 lock)

```bash
$ cd backend && DUFFEL_API_TOKEN= uv run python -c "from app.api.main import app; print('boot ok')"
JWT_SECRET is set to the default value 'changeme'. ...   # pre-existing dev-default warning
CORS_ALLOWED_ORIGINS is set to the development default ('http://localhost:5173'). ...
boot ok
```

Exit 0 with `boot ok` printed — confirms the lifespan does NOT raise on missing creds even when `DUFFEL_API_TOKEN` is empty.

### `/health` integration coverage

`backend/tests/integration/test_lifespan_flight_provider.py` (NEW, 80 LOC, 3 tests):

| Test | Branch | Assertions |
|------|--------|------------|
| `test_lifespan_uses_mock_when_duffel_env_is_mock` | explicit mock | flight_provider == "mock" + isinstance MockFlightAPIClient + caplog **absent** of `DUFFEL_API_TOKEN missing` |
| `test_lifespan_falls_back_to_mock_when_token_missing` | D-02 fallback | flight_provider == "mock" + isinstance MockFlightAPIClient + caplog **contains** `DUFFEL_API_TOKEN missing` |
| `test_lifespan_constructs_duffel_client_with_real_token` | real client | flight_provider == "real" + isinstance DuffelFlightClient + `_base_url == "https://api.duffel.com"` (token never inspected — T-07-03-01) |

`backend/tests/integration/test_health.py`: unchanged shape (2 tests still pass) — the docstring on `test_health_flight_provider_is_mock_without_credentials` was rewritten to drop the stale "Phase 7 vendor switch in progress" prose now that the Duffel client + D-02 fallback have landed.

## Tasks

### Task 1: D-02 lifespan auto-fallback + DuffelFlightClient construction

Single commit `0bed9c0`. `from app.flights.duffel_client import DuffelFlightClient` added to the import block. The Mock-only two-liner replaced with the D-02 branch.

mypy strict clean, ruff clean, ruff format clean. Boot smoke test passes.

The D-02 branch treats both `None` and empty `SecretStr('')` as "no token" via a guard expression that handles the empty-`.env.example` row case flagged in the Plan 07-01 SUMMARY. mypy initially complained about `SecretStr | None` narrowing across `or`; restructured to a local `duffel_token_value: str` variable so the narrow flows through cleanly without a `type: ignore`.

### Task 2: D-08 dead-code cleanup

Single commit `8ea4d81`. `normalize_amadeus_offer` + `normalize_skyscanner_itinerary` deleted from `flight_search.py`; `from datetime import UTC` + `from typing import Any` + `from datetime import datetime` removed (unused after deletion). The `_to_flight_search_result` docstring was rewritten to reference Duffel-aware data flow rather than the deleted "Phase 7's real Amadeus client will populate `city`..." prose.

In the test file, the two large fixtures (`AMADEUS_FLIGHT_OFFER` + `AMADEUS_DICTIONARIES` + `SKYSCANNER_ITINERARY`) were dropped together with the 6 tests that exercised them. `test_flight_search_module_no_amadeus_normalizers` was added at the top of the surviving file as the regression-lock.

mypy strict clean (after fixing one pre-existing dict-shape error in `test_flight_search_result_envelope_shape` that surfaced once the file was smaller — switched the `query=...` arg from a dict literal to a `FlightSearchQuery` instance). All 290 unit tests still pass.

### Task 3: Integration tests for lifespan branches + /health docstring refresh

Single commit `c0db8db`. The new test file uses `monkeypatch.setattr("app.config.settings.duffel_env", ...)` and `monkeypatch.setattr("app.config.settings.duffel_api_token", ...)` to drive the three branches; lifespan runs via `with TestClient(app) as client:` (the bare module-level constructor does NOT trigger lifespan).

`caplog.at_level(logging.WARNING, logger="app.api.main")` is used for the WARN-log assertion in the fallback-branch test and the silence-assertion in the explicit-mock-branch test.

The TDD `tdd="true"` marker on Task 3 was satisfied by writing tests immediately after Task 1's lifespan landed; per Plan 07-03's wave structure the tests pass green on first run because the production code from Task 1 is already in place.

mypy strict clean on all 5 verification-target files. ruff clean. ruff format clean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] mypy union-attr error on `SecretStr | None` narrowing**
- **Found during:** Task 1
- **Issue:** The plan's recommended branch `settings.duffel_api_token is None or not settings.duffel_api_token.get_secret_value()` does not narrow correctly for mypy strict — mypy sees the `.get_secret_value()` call as a possibly-`None` access across the `or`.
- **Fix:** Restructured to a local `duffel_token_value: str = duffel_token.get_secret_value() if duffel_token is not None else ""` and branched on `not duffel_token_value`. Same runtime semantics, narrows cleanly. No `type: ignore` needed.
- **Files modified:** `backend/app/api/main.py`
- **Commit:** `0bed9c0`

**2. [Rule 1 — Bug] Pre-existing mypy dict-shape error in `test_flight_search_result_envelope_shape`**
- **Found during:** Task 2 (mypy run after deletion)
- **Issue:** `FlightSearchResult(query={...})` — passing a dict literal to a field typed `FlightSearchQuery`. Pre-existing; surfaced once the file was smaller and easier to mypy-check. The acceptance criteria for Task 2 require zero mypy errors on the modified file.
- **Fix:** Switched the test to construct `FlightSearchQuery(...)` explicitly. No behavior change — pydantic accepted the dict at runtime via implicit validation.
- **Files modified:** `backend/tests/unit/test_tool_json_normalization.py`
- **Commit:** `8ea4d81`

**3. [Rule 1 — Plan inconsistency] WARN-message literal grep-count constraint**
- **Found during:** Task 1 (acceptance check)
- **Issue:** The acceptance criterion `grep -F 'DUFFEL_API_TOKEN missing' backend/app/api/main.py | wc -l` returns 1 conflicts with the natural pattern of also citing the literal in a nearby comment (which would push the count to 2).
- **Fix:** Reworded the comment above the `logger.warning(...)` call to reference "the literal log line below" instead of repeating the exact substring. Single grep match preserved without changing the WARN copy itself.
- **Files modified:** `backend/app/api/main.py`
- **Commit:** `0bed9c0`

### Documented inconsistencies (NOT auto-fixed)

**Acceptance criterion vs. regression-lock test (Task 2)**

The plan specifies BOTH:
- `grep -cE 'normalize_amadeus_offer|normalize_skyscanner_itinerary' backend/tests/unit/test_tool_json_normalization.py` returns `0`
- AND a regression-lock test that asserts `not hasattr(flight_search, "normalize_amadeus_offer")` and `not hasattr(flight_search, "normalize_skyscanner_itinerary")`.

These are mutually exclusive — the regression-lock test contains the literal strings by design. The grep returns **4** (two strings, two checks each in the docstring + asserts). The regression-lock is the substantive value (T-07-03-05 mitigation); the grep is the literal-removal proof for the implementation file. Implementation file `flight_search.py` returns **0** for the function-definition grep (`def normalize_amadeus_offer|def normalize_skyscanner_itinerary`) — the deletion is real. Documenting here so the inconsistency is on the record without blocking the plan.

## Threat Flags

None — this plan implements the mitigations declared in the plan's `<threat_model>` (T-07-03-01 through T-07-03-05) and does not introduce any new security-relevant surface beyond what was already authored.

T-07-03-01 (bearer-token leakage): the SecretStr unwrap call (`duffel_token.get_secret_value()`) is the only place in the codebase outside of tests that the raw token leaves SecretStr opacity. Plan 07-01's `ApiKeyScrubber` regex provides defense in depth on any accidental log line. The integration test `test_lifespan_constructs_duffel_client_with_real_token` asserts only `_base_url`, never the stored token.

## Self-Check: PASSED

**Files verified to exist:**
- `backend/app/api/main.py` — FOUND (modified)
- `backend/app/tools/flight_search.py` — FOUND (modified)
- `backend/tests/unit/test_tool_json_normalization.py` — FOUND (modified)
- `backend/tests/integration/test_lifespan_flight_provider.py` — FOUND (created)
- `backend/tests/integration/test_health.py` — FOUND (modified)

**Commits verified to exist (on `worktree-agent-a82053c3293a37720`):**
- `0bed9c0` feat(07-03): wire DuffelFlightClient into lifespan with D-02 auto-fallback
- `8ea4d81` refactor(07-03): D-08 cleanup — drop vendor-specific normalizers from flight_search.py
- `c0db8db` test(07-03): cover lifespan flight-provider branches + refresh /health docstring
