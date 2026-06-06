---
phase: 07-real-flight-api
plan: 04
subsystem: testing
tags: [duffel, e2e, ci, gated-tests, pyreqwest, github-actions, documentation]

requires:
  - phase: 07-real-flight-api
    provides: DuffelFlightClient (Plan 07-02), lifespan auto-fallback (Plan 07-03), Settings.duffel_* fields (Plan 07-01)
provides:
  - Gated real-API e2e suite at backend/tests/e2e_duffel/ (4 tests, D-12)
  - DuffelFlightClient._auth_probe — lightweight token verification via GET /air/airlines?limit=1
  - just test-duffel runner
  - duffel-e2e CI job gated on vars.DUFFEL_E2E_ENABLED == 'true'
  - README "Duffel Flight API (Phase 7)" section covering signup → local → CI
affects: [phase-08, future-vendor-clients, ci-strategy]

tech-stack:
  added: []  # No new packages — pyreqwest, pytest, GitHub Actions already in place.
  patterns:
    - "Pattern S5: path-isolated gated e2e suite with module-level pytestmark.skipif (replaces deleted Amadeus tests/e2e_amadeus/)"
    - "Two-toggle CI gate (vars.<VENDOR>_E2E_ENABLED + secrets.<VENDOR>_API_TOKEN); PR CI never requires the secret"
    - "_auth_probe via lightweight reference endpoint — no per-search quota burn"

key-files:
  created:
    - backend/tests/e2e_duffel/__init__.py
    - backend/tests/e2e_duffel/conftest.py
    - backend/tests/e2e_duffel/test_duffel_client.py
    - .planning/phases/07-real-flight-api/07-04-SUMMARY.md
  modified:
    - backend/app/flights/duffel_client.py
    - justfile
    - .github/workflows/ci.yml
    - README.md

key-decisions:
  - "Plan 07-04 owns DuffelFlightClient._auth_probe (option-B ownership) — Plan 07-02 deliberately did not add it; introducing the method here keeps it adjacent to the test that exercises it."
  - "Module-level pytestmark.skipif on test_duffel_client.py (not conftest-only) — pytest does not propagate conftest module variables into test files without explicit import, so the gate must live next to the tests it guards."
  - "_auth_probe uses GET /air/airlines?limit=1 (reference data, no offer-request quota) per RESEARCH OQ-1, keeping gated CI runs cheap regardless of sandbox quota policy."
  - "duffel-e2e job gated on vars.DUFFEL_E2E_ENABLED == 'true' at JOB level (not step level) so PR CI from external forks never requires the secret and never runs the job."

patterns-established:
  - "Pattern S5: gated vendor e2e — directory `tests/e2e_<vendor>/`, module-level pytestmark.skipif, dedicated justfile target, dedicated CI job gated on `vars.<VENDOR>_E2E_ENABLED`. Reusable for any future real-API integration."
  - "_auth_probe: lightweight reference-endpoint auth verification, distinct from health_check (which never issues outbound HTTP)."

requirements-completed: [REQ-real-flight-api]

duration: ~5 min
completed: 2026-06-06
---

# Phase 7 Plan 4: Gated Real-API e2e Suite Summary

**Gated Duffel real-API test suite (4 tests behind `pytest.mark.skipif(not DUFFEL_AVAILABLE)`), `DuffelFlightClient._auth_probe` via `GET /air/airlines?limit=1`, `just test-duffel` runner, two-toggle GitHub Actions job (`vars.DUFFEL_E2E_ENABLED` + `secrets.DUFFEL_API_TOKEN`), and a Duffel-credential-setup README section.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-06T05:23:30Z
- **Completed:** 2026-06-06T05:28:18Z
- **Tasks:** 2 (3 commits — TDD RED + GREEN for Task 1, single commit for Task 2)
- **Files modified:** 7 (4 created, 3 modified) — `duffel_client.py`, `justfile`, `.github/workflows/ci.yml`, `README.md` modified; `tests/e2e_duffel/{__init__,conftest,test_duffel_client}.py` and SUMMARY created.

## Accomplishments

- `tests/e2e_duffel/` package with `conftest.py` (module-scoped `duffel_client` fixture, `DUFFEL_AVAILABLE` flag) and `test_duffel_client.py` (four D-12 tests: `test_auth_probe`, `test_real_search_returns_results`, `test_vendor_neutral_shape`, `test_error_mapping_401_with_bogus_token`) gated at module level.
- `DuffelFlightClient._auth_probe` added between `health_check` and `_build_offer_request_body`. Issues `GET /air/airlines?limit=1` via the same pyreqwest builder shape as `_search_impl`, with `error_for_status(True)` and the same `_raise_from_http_status` error-translation block. Returns `True` on 2xx; raises the project's `APIError` hierarchy on non-2xx (D-04 mapping).
- `justfile` gains `test-duffel` target — 2-line addition appended after `test-integration`.
- `.github/workflows/ci.yml` gains a `duffel-e2e` job (sibling to `backend`/`frontend`/`e2e`) gated on `if: vars.DUFFEL_E2E_ENABLED == 'true'`. Pytest step reads `DUFFEL_API_TOKEN: ${{ secrets.DUFFEL_API_TOKEN }}` into env. PR CI never requires the secret because the job is fully skipped without admin opt-in.
- `README.md` "Phase 7 in flux" placeholder replaced with a Duffel-specific section: signup pointer, local `.env` / shell export, `DUFFEL_ENV=mock` override, `just test-duffel` invocation, two-step CI admin config (variable + secret), Pitfall 1 fallback note.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED — gated e2e suite scaffolding** — `90a7dcf` (test): empty `__init__.py`, `conftest.py` with `DUFFEL_AVAILABLE` + `duffel_client` fixture, `test_duffel_client.py` with module-level `pytestmark` and four async tests. Suite skips cleanly when `DUFFEL_API_TOKEN` is unset; references not-yet-implemented `_auth_probe` (RED state).
2. **Task 1 GREEN — `_auth_probe` implementation** — `1993799` (feat): adds `async def _auth_probe(self) -> bool` to `DuffelFlightClient`. Mirrors `_search_impl`'s pyreqwest chain shape, uses `error_for_status(True)`, translates `StatusError`/`RequestTimeoutError`/`ConnectError` via the existing `_raise_from_http_status` helper. mypy + ruff clean.
3. **Task 2 — runner, CI job, README** — `88c9713` (chore): `just test-duffel` target (justfile lines 32–34), `duffel-e2e` job (ci.yml lines 121–158 — `if: vars.DUFFEL_E2E_ENABLED == 'true'` at job level, `DUFFEL_API_TOKEN: ${{ secrets.DUFFEL_API_TOKEN }}` env on the pytest step), README "Duffel Flight API (Phase 7)" section (README lines 73–124).

_TDD note: Task 1 followed RED → GREEN. The RED commit (`90a7dcf`) introduces tests that reference an unimplemented `_auth_probe`; the suite skips cleanly with `DUFFEL_API_TOKEN` unset (collection-time gate), so RED is verified statically — a live run with a token would AttributeError on `_auth_probe`. The GREEN commit (`1993799`) adds the method, after which mypy and ruff pass on all touched files. No REFACTOR commit needed._

**Plan metadata commit:** TBD (orchestrator-managed final commit; this SUMMARY lands before that step).

## Files Created/Modified

- `backend/tests/e2e_duffel/__init__.py` — empty package marker for the path-isolated suite.
- `backend/tests/e2e_duffel/conftest.py` — `DUFFEL_AVAILABLE = bool(os.environ.get("DUFFEL_API_TOKEN"))` flag and module-scoped `duffel_client` fixture; docstring explicitly notes deliberate non-inheritance of the integration httpx stub (these tests issue real HTTP).
- `backend/tests/e2e_duffel/test_duffel_client.py` — module-level `pytestmark = pytest.mark.skipif(not DUFFEL_AVAILABLE, reason="DUFFEL_API_TOKEN not set")` + four async tests covering D-12(a)–(d). Bogus-token test constructs its own client (not the fixture) so a leaked invalid token in trace output is harmless.
- `backend/app/flights/duffel_client.py` — `_auth_probe` method added at line 201 (between `health_check` and `_build_offer_request_body`); 50-line addition. Comment near `health_check` cross-references the new method.
- `justfile` — `test-duffel` target appended after `test-integration` (lines 32–34).
- `.github/workflows/ci.yml` — `duffel-e2e` job appended after `e2e` (lines 121–158); job-level `if: vars.DUFFEL_E2E_ENABLED == 'true'` and step-level `env.DUFFEL_API_TOKEN: ${{ secrets.DUFFEL_API_TOKEN }}`.
- `README.md` — "Real Flight API (Phase 7 — in flux)" placeholder section replaced with a 52-line "Duffel Flight API (Phase 7)" section (lines 73–124) covering signup, local config, local test run, CI admin config, and Pitfall 1.

## Decisions Made

- **Plan 07-04 owns `_auth_probe`** (option-B ownership). Plan 07-02 built the rest of the client but intentionally did not define this method; introducing it adjacent to the test that exercises it (D-12) keeps cause and effect in one commit.
- **Module-level `pytestmark` (not conftest-only)**. Conftest module variables aren't visible to test modules without an explicit import, so the skip gate lives next to the tests it guards. This matches the historical Amadeus suite shape (`5d7499c^:tests/e2e_amadeus/`) and the PATTERNS.md S5 prescription.
- **`_auth_probe` via reference data**. `GET /air/airlines?limit=1` is reference data and is not subject to the offer-request quota (RESEARCH OQ-1). This keeps gated CI runs cheap and avoids burning sandbox quota for a liveness signal.
- **Job-level `if:` gate**. The `duffel-e2e` job is fully skipped via `if: vars.DUFFEL_E2E_ENABLED == 'true'` at the job (not step) level. PR CI from forks never requires the secret because the job never runs without an admin opt-in.

## Deviations from Plan

None — plan executed exactly as written. The verification grep for `vars\.DUFFEL_E2E_ENABLED` in README.md initially returned `0` because the first README draft elided the `vars.` prefix from the prose; this was caught during Task 2 verification (still inside the same task's edit window) and corrected before the Task 2 commit. No separate deviation entry needed — the criterion was satisfied at commit time.

## Issues Encountered

None. Worktree was already on `worktree-agent-a02fe1c77102b4ce4`, base reset succeeded, all verification gates passed first try.

## Suite-Skip Verification (token unset)

```
$ env -u DUFFEL_API_TOKEN uv run pytest tests/e2e_duffel/ -v
collected 4 items

tests/e2e_duffel/test_duffel_client.py::test_auth_probe SKIPPED (DUFFEL_API_TOKEN not set)
tests/e2e_duffel/test_duffel_client.py::test_real_search_returns_results SKIPPED
tests/e2e_duffel/test_duffel_client.py::test_vendor_neutral_shape SKIPPED
tests/e2e_duffel/test_duffel_client.py::test_error_mapping_401_with_bogus_token SKIPPED

============================== 4 skipped in 0.01s ==============================
```

This is the default behaviour for fresh checkouts and PR CI — the gate fires at module import (the four test bodies never execute, no real HTTP issued). With `DUFFEL_API_TOKEN=duffel_test_<real>` set, the same command would run all four tests live; that path was NOT exercised during this plan because no sandbox token was available to the executor (developer-driven verification documented in Task 2 acceptance criteria).

## Live Test Results

Not exercised. No `DUFFEL_API_TOKEN` was provided to the executor. The four tests are statically valid (mypy + ruff clean, suite collects and skips deterministically); a developer with a Duffel sandbox account can confirm live behaviour by exporting `DUFFEL_API_TOKEN` and running `just test-duffel`.

## Verification Run Summary

| Check | Command | Result |
|-------|---------|--------|
| Suite skip with token unset | `env -u DUFFEL_API_TOKEN uv run pytest tests/e2e_duffel/ -v` | 4 skipped, 0 failed |
| mypy | `uv run mypy app/flights/duffel_client.py tests/e2e_duffel/` | 0 issues, 4 source files |
| Full mypy app/ | `uv run mypy app/` | 0 issues, 40 source files |
| Ruff lint | `uv run ruff check app/flights/duffel_client.py tests/e2e_duffel/` | All checks passed |
| Ruff format | `uv run ruff format --check app/flights/duffel_client.py tests/e2e_duffel/` | 4 files already formatted |
| Duffel unit tests still green | `uv run pytest tests/unit/test_duffel_client.py tests/unit/test_duffel_error_mapping.py` | 19 passed |
| YAML well-formed | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` | Exit 0 |
| justfile target | `grep -cE '^test-duffel:' justfile` | 1 |
| CI job present | `grep -cE 'duffel-e2e:' .github/workflows/ci.yml` | 1 |
| CI gate | `grep -cE "vars\\.DUFFEL_E2E_ENABLED == 'true'" .github/workflows/ci.yml` | 1 |
| CI secret env | `grep -cE 'DUFFEL_API_TOKEN: \\$\\{\\{ secrets\\.DUFFEL_API_TOKEN \\}\\}' .github/workflows/ci.yml` | 1 |
| README references | `grep -cE 'DUFFEL_API_TOKEN' README.md` | 5 (≥ 2 required) |
| README CI var prose | `grep -cE 'vars\\.DUFFEL_E2E_ENABLED' README.md` | 2 (≥ 1 required) |

## User Setup Required

None for code correctness. Optional admin actions to enable live verification:

- **Local developer with sandbox account.** Set `DUFFEL_API_TOKEN=duffel_test_...` in `.env` (gitignored) and run `just test-duffel`. Documented in README.
- **Repo admin (CI live coverage).** In GitHub → Settings → Secrets and variables → Actions, add the variable `DUFFEL_E2E_ENABLED=true` and the secret `DUFFEL_API_TOKEN=duffel_test_...`. The `duffel-e2e` job will start running on subsequent pushes; PRs from external forks remain unaffected.

## Threat Surface Scan

No new threat surface beyond what 07-04-PLAN.md's `<threat_model>` enumerated. The four registered threats remain accurate:

- T-07-04-01 (token leakage in CI logs): mitigated by `ApiKeyScrubber` (Plan 07-01) + the bogus-token test using a synthetic invalid token.
- T-07-04-02 (token in fixtures or YAML): no real token is committed; CI YAML uses `${{ secrets.DUFFEL_API_TOKEN }}` exclusively.
- T-07-04-03 (PR fork exfiltration): default GitHub Actions behaviour does not expose secrets to fork PRs; the `duffel-e2e` job is additionally gated on `vars.DUFFEL_E2E_ENABLED`.
- T-07-04-04 (sandbox quota burn): `_auth_probe` uses reference data; live tests issue exactly 4 requests per CI run.
- T-07-04-05 (silent green when var unset): accepted; documented in README CI section.
- T-07-04-06 (invalid YAML breaks CI): mitigated by the `python3 -c "import yaml; yaml.safe_load(...)"` smoke check.

## Next Phase Readiness

- `_auth_probe` is available for future health-check elaboration (e.g., a Phase 8 admin-only `/health/duffel/auth` endpoint could call it on demand).
- `tests/e2e_duffel/` is the canonical location for any future Duffel-specific live tests (e.g., booking flow when `BookingClass` graduates beyond search).
- Pattern S5 (path-isolated gated e2e) is reusable for the next vendor: copy the directory shape, update `_auth_probe`'s endpoint, add a sibling `vars.<VENDOR>_E2E_ENABLED` toggle.
- No blockers. Phase 7 is functionally complete; verification phase (`/gsd-verify-work`) can now run.

## Self-Check: PASSED

- `[x]` `backend/tests/e2e_duffel/__init__.py` exists (0 bytes, empty package marker).
- `[x]` `backend/tests/e2e_duffel/conftest.py` exists (40 lines).
- `[x]` `backend/tests/e2e_duffel/test_duffel_client.py` exists (104 lines, 4 tests, module-level pytestmark).
- `[x]` `_auth_probe` present in `backend/app/flights/duffel_client.py` at line 201.
- `[x]` `test-duffel` target present in `justfile` at lines 32–34.
- `[x]` `duffel-e2e` job present in `.github/workflows/ci.yml` at lines 121–158.
- `[x]` `### Duffel Flight API (Phase 7)` section present in `README.md` at line 73.
- `[x]` Commit `90a7dcf` (test) — confirmed via `git log --oneline | grep 90a7dcf`.
- `[x]` Commit `1993799` (feat) — confirmed via `git log --oneline | grep 1993799`.
- `[x]` Commit `88c9713` (chore) — confirmed via `git log --oneline | grep 88c9713`.
- `[x]` All listed verification commands ran successfully.

---
*Phase: 07-real-flight-api*
*Plan: 04*
*Completed: 2026-06-06*
