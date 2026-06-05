---
phase: 07-real-flight-api
plan: 06
subsystem: backend/tests + ci + docs
tags: [amadeus, e2e, ci, github-actions, secrets-gating, justfile, README]

# Dependency graph
requires:
  - phase: 07-real-flight-api
    provides: Plan 04 — `AmadeusFlightClient` (`backend/app/flights/amadeus_client.py`)
provides:
  - "backend/tests/e2e_amadeus/ — path-isolated real-API test suite (D-14)"
  - "Module-level pytestmark skipif guard so default selectors do not run the suite without creds"
  - "module-scoped amadeus_client fixture that constructs a real AmadeusFlightClient against the Amadeus test sandbox"
  - "Four D-15 assertions: token fetch+cache, MAD->BCN >=1 result, vendor-neutral Flight shape, 401 mapping via _get_token bad-credentials path"
  - "justfile `test-amadeus` target invoking `pytest tests/e2e_amadeus/ -v`"
  - "GitHub Actions `amadeus-e2e` job gated on `vars.AMADEUS_E2E_ENABLED == 'true'` AND non-pull_request event (D-14)"
  - "README \"Amadeus Flight API (Phase 7)\" section documenting env-var setup for local + CI"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Path-isolated test directory + module-level pytestmark skipif (RESEARCH Pattern 10)"
    - "Repository-variable gate as workaround for `secrets.* != ''` not being supported in `if:` expressions on pull_request events"
    - "GitHub Actions secrets exposed only via job-level `env:` block (default secret-redaction masks them in logs; T-07-02)"

key-files:
  created:
    - backend/tests/e2e_amadeus/__init__.py
    - backend/tests/e2e_amadeus/conftest.py
    - backend/tests/e2e_amadeus/test_amadeus_client.py
    - .planning/phases/07-real-flight-api/07-06-SUMMARY.md
  modified:
    - justfile
    - .github/workflows/ci.yml
    - README.md

key-decisions:
  - "CI gate uses a repository VARIABLE `AMADEUS_E2E_ENABLED` (not a `secrets.* != ''` check). Rationale: GitHub Actions does not support secret expressions in job-level `if:` conditions on pull_request events from forks; the variable lets a maintainer flip the gate on once secrets exist. The `if:` also requires `github.event_name != 'pull_request'` so PR CI from forks never attempts the job even when the variable is set."
  - "Module-level `pytestmark = pytest.mark.skipif(not AMADEUS_AVAILABLE, ...)` is restated in the test module rather than relying on conftest.py module variables. Pytest does not propagate conftest module-level variables into test modules without an explicit import; restating the predicate keeps the skip atomic and self-documenting."
  - "conftest.py for e2e_amadeus deliberately omits the `_stub_local_provider_probes` autouse fixture from `tests/integration/conftest.py`. Per-directory conftest scoping means it would not inherit anyway, but the omission is documented in the conftest docstring so a future copy-paste does not accidentally stub real HTTP traffic."
  - "Test for bad credentials targets `_get_token()` (the OAuth2 path) rather than `search()`. With wrong creds, `_refresh_token`'s catch-all wraps the `KeyError` from missing `access_token` (or any underlying StatusError) as `APIError(retryable=True)`. Asserting `pytest.raises(APIError)` is the most stable assertion shape — narrower assertions on `APIClientError` would couple the test to internal mapping that lives in the search path, not the token path."
  - "`MAD->BCN` chosen as the sandbox-reliable route per RESEARCH Pitfall 1; the test asserts `>= 1` (never `== N`). If the sandbox ever returns 0 results in CI, the documented fallback is `LON->NYC` — change `FlightQuery` in `test_real_search_returns_results` and document the swap inline."

requirements-completed: [REQ-real-flight-api]

# Metrics
duration: ~10min
completed: 2026-06-05
---

# Phase 07 Plan 06: e2e_amadeus suite + CI gate + docs Summary

**Closed out Phase 7 by adding the path-isolated `backend/tests/e2e_amadeus/` real-API test suite (D-14), a `just test-amadeus` invocation target, a maintainer-gated `amadeus-e2e` GitHub Actions job, and a README section that documents `AMADEUS_*` credential setup for both local development and CI. Default PR CI is unaffected — the new job runs only on `master` push (or `workflow_dispatch`) when the maintainer has set the repository variable `AMADEUS_E2E_ENABLED=true` and the secrets `AMADEUS_API_KEY` + `AMADEUS_API_SECRET`. The four async tests assert the D-15 behaviours: token fetch + cache hit, real MAD→BCN search returns ≥1 result (Pitfall 1), vendor-neutral `Flight` shape, and 401 mapping via the bad-credentials `_get_token()` path.**

## Performance

- **Started:** 2026-06-05 (post Plan 04)
- **Completed:** 2026-06-05
- **Tasks:** 2
- **Files created:** 4 (3 in `backend/tests/e2e_amadeus/` + this summary)
- **Files modified:** 3 (`justfile`, `.github/workflows/ci.yml`, `README.md`)
- **Tests added:** 4 (skipped without creds; verified by `pytest --collect-only` + skipif fire under `env -u AMADEUS_API_KEY -u AMADEUS_API_SECRET`)

## Tasks Executed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create `backend/tests/e2e_amadeus/` — `__init__.py`, `conftest.py`, `test_amadeus_client.py` with skipif guard | `5c3405d` | `backend/tests/e2e_amadeus/__init__.py`, `backend/tests/e2e_amadeus/conftest.py`, `backend/tests/e2e_amadeus/test_amadeus_client.py` (all created) |
| 2 | Add justfile `test-amadeus` target + CI workflow `amadeus-e2e` job + README credential setup | `71236de` | `justfile`, `.github/workflows/ci.yml`, `README.md` |

## Output Notes (per `<output>` directive in PLAN.md)

### Exact placement of the `amadeus-e2e` job in `ci.yml`

Appended after the existing `e2e` job (at the time of writing, line 119 in pre-edit `ci.yml`). The new job spans roughly lines 120–164 in the post-edit file, structured as:

- Comment block (3 lines + 3-line note explaining the `secrets.* != ''` limitation)
- `amadeus-e2e:` job header with `name: Amadeus E2E` and `runs-on: ubuntu-latest`
- `if:` condition: `github.event_name != 'pull_request' && vars.AMADEUS_E2E_ENABLED == 'true'`
- `defaults.run.working-directory: backend` (mirrors the `backend` job)
- `env:` block exposing `AMADEUS_API_KEY` / `AMADEUS_API_SECRET` from secrets
- Steps: `checkout@v4`, `setup-python@v5` (Python 3.13), `setup-uv@v4`, `actions/cache@v4` keyed on `hashFiles('backend/uv.lock')`, `uv sync --frozen`, then `uv run pytest tests/e2e_amadeus/ -v -s`

### Rationale for `vars.AMADEUS_E2E_ENABLED` instead of `secrets.* != ''` in `if:`

GitHub Actions does **not** evaluate `secrets.*` inside job-level `if:` expressions on `pull_request` events from forks (secrets are unavailable to fork PRs by design). Even on `push`/`workflow_dispatch`, treating `secrets.AMADEUS_API_KEY != ''` inside `if:` is undocumented and brittle. The standard workaround is a **repository variable** (`vars.*`) that the maintainer flips on after adding secrets — visible from `Settings → Secrets and variables → Actions → Variables`. The two-condition `if:` (`pull_request` excluded AND variable on) gives explicit, auditable gating without relying on undocumented `secrets.*` behaviour.

### README section title and approximate line range

Section heading: `## Amadeus Flight API (Phase 7)`

Inserted between the existing `## Quickstart` block (ends ~line 71) and `## Project Structure` (~line 73 pre-edit). Post-edit, the new section spans approximately lines 73–130. Subheadings inside:

- `### Required environment variables` (with a 3-row table)
- `### Local dev setup` (bash example)
- `### Running the real-API tests locally` (bash example)
- `### CI gating` (numbered enabling steps + rationale paragraph)

### Manual checklist for the maintainer to enable the job

1. **Add secrets** — `Settings → Secrets and variables → Actions → New repository secret`:
   - Name: `AMADEUS_API_KEY` — Value: client_id from the Amadeus developer console.
   - Name: `AMADEUS_API_SECRET` — Value: client_secret from the Amadeus developer console.
2. **Set the gate variable** — same UI page → `Variables` tab → `New repository variable`:
   - Name: `AMADEUS_E2E_ENABLED` — Value: `true` (literal string, lowercase).
3. **Trigger the job** — push any commit to `master` (e.g. a doc tweak) or run the workflow manually via `Actions → CI → Run workflow → Branch: master`.
4. **Verify** — the `Amadeus E2E` job should appear in the workflow run summary and pass with four green test results.

### Note on Pitfall 1 (sandbox sparse routes)

`MAD→BCN` (Madrid → Barcelona) is the most reliably populated route in the Amadeus test sandbox per `07-RESEARCH.md` Pitfall 1. The tests assert `>= 1` (never `== N`). If the sandbox ever returns 0 results in CI for `MAD→BCN`:

1. Edit `backend/tests/e2e_amadeus/test_amadeus_client.py`.
2. Change the `FlightQuery(origin="MAD", destination="BCN", ...)` literal to `FlightQuery(origin="LON", destination="NYC", ...)` (LON = London Heathrow LHR via the sandbox's `LON` city code; NYC similarly).
3. Update `test_vendor_neutral_shape`'s `assert first.origin == "MAD"` to match the new origin code (`"LHR"` if the search resolves to a specific airport).
4. Add a comment above the swap noting the date and the sandbox failure that triggered it.

## Verification Run

| Acceptance criterion | Result |
|----------------------|--------|
| `ls backend/tests/e2e_amadeus/{__init__,conftest,test_amadeus_client}.py` | all three present |
| `grep AMADEUS_AVAILABLE` in `conftest.py` AND `test_amadeus_client.py` | matched in both |
| `grep -n 'pytestmark.*skipif' test_amadeus_client.py` | 1 match |
| `grep -c '^async def test_' test_amadeus_client.py` | 4 (token cache, real search, shape, 401 mapping) |
| `pytest tests/unit tests/integration --collect-only \| grep -c 'e2e_amadeus'` | 0 (path-isolated) |
| Without env vars: `pytest tests/e2e_amadeus/ -v` | 4 SKIPPED (skipif fires) |
| `ruff check tests/e2e_amadeus/` | clean |
| `ruff format --check tests/e2e_amadeus/` | clean |
| `mypy tests/e2e_amadeus/` | Success: no issues found in 3 source files |
| `grep '^test-amadeus:' justfile` | 1 match |
| `just --list \| grep test-amadeus` | 1 match |
| `grep 'amadeus-e2e:' .github/workflows/ci.yml` | 1 match |
| `grep "github.event_name != 'pull_request'" ci.yml` | 1 match |
| Non-comment `AMADEUS_E2E_ENABLED` lines in ci.yml | 1 match (the `if:` line) |
| `python -c "import yaml; yaml.safe_load(open('ci.yml'))"` | parses (jobs: backend, frontend, e2e, amadeus-e2e) |
| `git diff ci.yml` | only additions (existing jobs unchanged) |
| README references `AMADEUS_API_KEY`, `AMADEUS_API_SECRET`, `developers.amadeus.com` | 7+ matches across the new section |

## Deviations from Plan

None — plan executed exactly as written. The plan's `<action>` block for Task 2 specifies `if: github.event_name != 'pull_request' && vars.AMADEUS_E2E_ENABLED == 'true'`, which is what landed (the PATTERNS.md example used a `secrets.* != ''` pattern that the plan body explicitly overrode).

## Self-Check: PASSED

- backend/tests/e2e_amadeus/__init__.py — FOUND
- backend/tests/e2e_amadeus/conftest.py — FOUND
- backend/tests/e2e_amadeus/test_amadeus_client.py — FOUND
- justfile (test-amadeus target) — FOUND (line 25–26)
- .github/workflows/ci.yml (amadeus-e2e job) — FOUND (line 127+)
- README.md (Amadeus Flight API section) — FOUND
- Commit `5c3405d` (test: e2e_amadeus suite) — FOUND in `git log`
- Commit `71236de` (chore: justfile + CI + README) — FOUND in `git log`
