---
phase: 07-real-flight-api
plan: 02
subsystem: backend/config
tags: [config, settings, secretstr, amadeus, security]
requires: []
provides:
  - "Settings.amadeus_env: Literal['test','prod','mock'] = 'test'"
  - "Settings.amadeus_api_key: SecretStr | None = None"
  - "Settings.amadeus_api_secret: SecretStr | None = None"
affects:
  - backend/app/config.py
tech-stack:
  added: []
  patterns:
    - "pydantic.SecretStr for credential scrubbing"
    - "typing.Literal for env-value narrowing (SSRF mitigation)"
key-files:
  created:
    - backend/tests/unit/test_config.py
  modified:
    - backend/app/config.py
decisions:
  - "Hardcoded breaker thresholds (D-12) deferred to Plan 03 — no amadeus_breaker_* knobs added per CONTEXT 'Claude's Discretion' guidance."
  - "Existing `openai_api_key: str | None` left as plain str — only the new Amadeus credentials adopt SecretStr (scope-limited to T-07-02 mitigation)."
metrics:
  duration_seconds: 212
  tasks_completed: 2
  files_modified: 1
  files_created: 1
  completed_date: 2026-06-05
---

# Phase 07 Plan 02: Amadeus Settings Fields Summary

Added three new fields to `Settings` (`amadeus_env`, `amadeus_api_key`, `amadeus_api_secret`) using `Literal` narrowing for SSRF defence and `SecretStr` for credential scrubbing, plus a focused unit-test module covering both mitigations.

## Tasks Executed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add amadeus_env / amadeus_api_key / amadeus_api_secret to Settings | `484c486` | `backend/app/config.py` |
| 2 | Add Settings tests for Literal narrowing + SecretStr scrubbing | `09d0dd9` | `backend/tests/unit/test_config.py` (created) |

## Implementation Notes

- **`backend/tests/unit/test_config.py` was CREATED** — the file did not exist prior to this plan. New tests are the only contents of the file.
- **Insertion point in `backend/app/config.py`**: the new `# Amadeus Flight API` comment block + three field declarations were inserted at lines 100–111, immediately AFTER the existing `openai_o_series_model_prefixes` field (now line 98) and BEFORE the `model_post_init` method (now line 113). The Literal field is at line 109; SecretStr fields are lines 110–111.
- **Imports added**: `from typing import Literal` (new line 4) and `SecretStr` was added to the existing `from pydantic import ...` line (line 6).
- **Downstream caller note**: code that needs the actual Amadeus credentials (Plan 03 lifespan, Plan 04 client construction, Plan 05 healthcheck) MUST call `.get_secret_value()` on `settings.amadeus_api_key` / `settings.amadeus_api_secret`. Raw access (e.g. `f"{settings.amadeus_api_key}"`) yields the literal string `'**********'` and will fail authentication silently if used as a header value.
- **Test isolation**: every test passes `_env_file=None` to `Settings(...)` so an exported `AMADEUS_*` env var on the developer's host cannot mask a regression. This also makes the tests stable in CI (where no `.env` is present).

## Verification Performed

- `uv run mypy app/config.py` — strict, no issues.
- `uv run ruff check app/config.py tests/unit/test_config.py` — clean.
- `uv run pytest tests/unit/test_config.py -k amadeus -v` — 7/7 passed (one parametrize fans into 3).
- `uv run pytest tests/unit/ -x --tb=short` — 268 passed, 1 skipped (no regressions across the full unit suite).
- Behaviour smoke check: `Settings(amadeus_env='test', amadeus_api_key='kkk', amadeus_api_secret='sss')` round-trips; `str(.amadeus_api_key) == '**********'`; `.get_secret_value() == 'kkk'`.
- Acceptance grep checks: `Literal[...]` present, `SecretStr` import + 2 fields present, `def test_amadeus` count = 5 (≥ 5 required).

## Threat-Model Alignment

| Threat | Status | Where verified |
|--------|--------|----------------|
| T-07-01 (Tampering — `amadeus_env` SSRF base-URL injection) | Mitigated | `test_amadeus_env_rejects_invalid_value` raises `ValidationError`; only `test`/`prod`/`mock` are accepted. |
| T-07-02 (Information Disclosure — credential leakage via str/repr) | Mitigated | `test_amadeus_api_key_secretstr_scrubs_str` proves the plaintext does not appear in either `str(...)` or `repr(...)`; `.get_secret_value()` is the sole legitimate read path. |
| T-07-SC (Supply chain — new imports) | Accepted | No new packages; `pydantic` (SecretStr) and `typing` (Literal) are already in `pyproject.toml`. |

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed; no checkpoints triggered.

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/config.py` — FOUND (modified at lines 4, 6, 100–111).
- `backend/tests/unit/test_config.py` — FOUND (created).
- Commit `484c486` (Task 1 — feat) — FOUND in `git log`.
- Commit `09d0dd9` (Task 2 — test) — FOUND in `git log`.
- All plan-level verification commands ran green.
