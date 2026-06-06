---
phase: 07-real-flight-api
plan: 01
subsystem: config + log-scrubbing
tags: [duffel, config, secrets, log-scrubbing, phase-7]
requirements: [REQ-real-flight-api]
dependency_graph:
  requires:
    - "backend/app/config.py::Settings (existing)"
    - "backend/app/llm/log_scrubbing.py::SECRET_PATTERNS (existing)"
  provides:
    - "Settings.duffel_api_token (SecretStr | None)"
    - "Settings.duffel_env (Literal['test','live','mock'])"
    - "ApiKeyScrubber Duffel bearer-token redaction"
    - ".env.example DUFFEL_API_TOKEN + DUFFEL_ENV documentation"
  affects:
    - "Plan 07-03 lifespan auto-fallback (consumes duffel_api_token + duffel_env)"
    - "Plan 07-04 README credential setup (references DUFFEL_API_TOKEN)"
    - "Plan 07-05 e2e_duffel suite (gated on DUFFEL_API_TOKEN)"
tech_stack:
  added: []
  patterns:
    - "SecretStr for credential opacity in repr() (T-07-02-class)"
    - "Literal-narrowed env selector (D-01)"
    - "regex tuple addition to SECRET_PATTERNS (Pitfall 7)"
key_files:
  created:
    - "backend/tests/unit/test_config_duffel.py"
  modified:
    - "backend/app/config.py"
    - "backend/app/llm/log_scrubbing.py"
    - "backend/tests/unit/llm/test_log_scrubbing.py"
    - ".env.example"
decisions:
  - "Comment block explains both defence layers (SecretStr + scrubber regex) at the Settings field site so a future reader sees the threat-model wiring without grepping the threat register."
  - "Empty DUFFEL_API_TOKEN= placeholder in .env.example yields SecretStr('') rather than None; Plan 07-03 lifespan must treat empty SecretStr as 'no token'. Flagged for the lifespan plan."
metrics:
  duration_minutes: 12
  tasks_completed: 3
  tests_added: 10
  completed_date: "2026-06-06"
---

# Phase 7 Plan 1: Duffel Settings + Log Scrubber Summary

Phase 7's credential surface lands: two `Settings` fields for the Duffel API token and environment selector, plus a one-line `ApiKeyScrubber` regex extension that redacts `duffel_test_*` and `duffel_live_*` bearer tokens at the log-formatter boundary, all documented in `.env.example`.

## What Shipped

### Final field declarations

```python
# backend/app/config.py — adjacent to anthropic_api_key
duffel_api_token: SecretStr | None = None
duffel_env: Literal["test", "live", "mock"] = "test"
```

The `SecretStr` import was added to the existing `from pydantic import field_validator` line; `Literal` was added via a new `from typing import Literal` import.

### Regex tuple added (verbatim)

Appended to `SECRET_PATTERNS` in `backend/app/llm/log_scrubbing.py`:

```python
(re.compile(r"duffel_(test|live)_[A-Za-z0-9_-]{20,}"), "duffel_[REDACTED]")
```

`SECRET_PATTERNS` length grew from 3 → 4. The `{20,}` lower bound is a deliberate false-positive guard: short literal substrings like the bare prefix in a debug message are NOT redacted.

### `.env.example` block

```
# Duffel Flight API (Phase 7 — D-01).
# Token is OPTIONAL: when unset, the lifespan auto-falls-back to MockFlightAPIClient
# (D-02), so a fresh checkout boots without a Duffel account. Token format is
# duffel_test_* (sandbox) or duffel_live_* (production); the prefix selects the
# environment. See README "Duffel credential setup" (Plan 07-04) for signup flow.
DUFFEL_API_TOKEN=
# DUFFEL_ENV selects the runtime mode. Valid values: test | live | mock.
# Default is "test" (sandbox); set to "mock" to force MockFlightAPIClient even
# when DUFFEL_API_TOKEN is set (useful for tests with real creds in env).
# DUFFEL_ENV=test
```

### Test count delta

| File | Tests before | Tests after | Delta |
|------|--------------|-------------|-------|
| `backend/tests/unit/test_config_duffel.py` (NEW) | 0 | 5 | +5 |
| `backend/tests/unit/llm/test_log_scrubbing.py` | 28 | 33 | +5 |

10 new tests total. All 38 tests in the two files pass.

### Confirmation that `Settings()` boots with no DUFFEL_* env vars present

Verified locally:

```bash
$ cd backend && uv run python -c "from app.config import Settings; s = Settings(duffel_api_token=None); assert s.duffel_api_token is None; assert s.duffel_env == 'test'"
# (no output; exit 0)
```

`Settings()` instantiation does not raise `ValidationError` when `DUFFEL_API_TOKEN` is unset (Pitfall 6 mitigation locked).

## Tasks

### Task 1: `duffel_api_token` + `duffel_env` Settings fields

**TDD:** RED commit `a1d3846` (5 failing tests) → GREEN commit `360e3f5` (Settings fields land).

5 unit tests cover: None default, SecretStr opacity in `repr()` (T-07-02-class), default `duffel_env == "test"`, `Literal` narrowing rejection of `staging`, and `mock` literal acceptance.

mypy strict clean on `app/config.py`. ruff lint + format clean.

### Task 2: ApiKeyScrubber Duffel bearer redaction

**TDD:** RED commit `e08f07f` (5 failing tests, including `len(SECRET_PATTERNS) == 4`) → GREEN commit `30b3589` (regex appended).

5 new Group A tests: `duffel_test_*` redaction, `duffel_live_*` redaction, short-prefix false-positive guard, Authorization-header format, and an OpenAI-key regression-lock asserting the new pattern did not break the existing `sk-` ordering.

All 33 pre-existing log-scrubber tests still pass. mypy + ruff clean.

### Task 3: `.env.example` documentation

Single commit `2c4eec6` — appended `Phase 7 — D-01` block after the `JWT_SECRET` row, with a 4-line comment header, an empty `DUFFEL_API_TOKEN=` row, and a commented `# DUFFEL_ENV=test` row that documents the three Literal values.

## Deviations from Plan

None — plan executed exactly as written.

(Minor inline adjustment, not a deviation: the comment block in `log_scrubbing.py` initially included the literal regex pattern, which made `grep -cE 'duffel_\(test\|live\)_\[A-Za-z0-9_-\]\{20,\}'` return 2 instead of the acceptance-criterion-required 1. Reworded the comment to reference the pattern in prose so the literal regex appears exactly once in the file.)

## Threat Flags

None — this plan implements the mitigations declared in the plan's `<threat_model>` (T-07-01-01 through T-07-01-05) and does not introduce new security-relevant surface beyond what was already authored. The empty `DUFFEL_API_TOKEN=` placeholder in `.env.example` is a documented design choice, not a new disclosure surface.

## Notes for Plan 07-03 (lifespan)

When the lifespan branches on `Settings.duffel_api_token`, treat **both** `None` and `SecretStr('')` as "no token" — the empty `DUFFEL_API_TOKEN=` row in `.env.example` produces a `SecretStr('')`, not `None`. The auto-fallback condition becomes:

```python
no_token = settings.duffel_api_token is None or not settings.duffel_api_token.get_secret_value()
if settings.duffel_env == "mock" or no_token:
    ...
```

Documented here so Plan 07-03 captures the empty-string case in its truth table.

## Self-Check: PASSED

**Files verified to exist:**
- `backend/tests/unit/test_config_duffel.py` — FOUND
- `backend/app/config.py` — FOUND (modified)
- `backend/app/llm/log_scrubbing.py` — FOUND (modified)
- `backend/tests/unit/llm/test_log_scrubbing.py` — FOUND (modified)
- `.env.example` — FOUND (modified)

**Commits verified to exist (on `worktree-agent-a10cf95052c4b5c8f`):**
- `a1d3846` test(07-01): add failing tests for duffel Settings fields
- `360e3f5` feat(07-01): add duffel_api_token + duffel_env Settings fields
- `e08f07f` test(07-01): add failing tests for duffel bearer token scrubbing
- `30b3589` feat(07-01): redact duffel bearer tokens in ApiKeyScrubber
- `2c4eec6` docs(07-01): document DUFFEL_API_TOKEN + DUFFEL_ENV in .env.example
