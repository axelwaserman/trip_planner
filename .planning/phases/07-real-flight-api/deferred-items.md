# Phase 07 Deferred Items

Out-of-scope discoveries surfaced during plan execution. These are NOT
fixed by the originating plan; they are logged here per the executor's
SCOPE BOUNDARY rule and are eligible for a future cleanup plan.

## From plan 07-07 (gap closure for CR-01 + CR-02)

### Pre-existing `ruff format` violations

`just check` fails on the baseline `18a9096` (pre-Plan-07-07) commit
because five files would be reformatted by `ruff format`:

- `backend/app/api/main.py` — untouched by Plan 07-07.
- `backend/app/flights/amadeus_client.py` — touched by Plan 07-07; the
  format issue exists in the surrounding `async with ClientBuilder()`
  block (lines 462+) and was inherited from the original Plan 07-04
  implementation. The new `_refresh_token` code added in Plan 07-07
  matches that pre-existing style for consistency, so it also surfaces
  as "would reformat".
- `backend/tests/integration/test_lifespan_flight_provider.py` —
  untouched by Plan 07-07.
- `backend/tests/unit/test_amadeus_client.py` — touched by Plan 07-07
  to add `test_search_offset_returns_correct_slice`. The format issues
  flagged by ruff are in pre-existing test bodies (e.g., the
  `test_circuit_breaker_open_raises_apiservererror_not_retried`
  inline-multiline `FlightQuery(...)` and the
  `test_unknown_cabin_falls_back_to_economy` `weird_offer` dict),
  not in the new test code added by 07-07.
- `backend/tests/unit/test_amadeus_error_mapping.py` — untouched by
  Plan 07-07.

`uv run ruff check` (lint) and `uv run mypy` (types) both pass. Only
`uv run ruff format --check` flags these files — and only because of
pre-existing code that violates the project's current `ruff format`
default. This appears to be a low-priority style drift accumulated
across earlier plans; a focused `chore(07): apply ruff format`
cleanup pass would close it without code-behavior risk.

**Action:** Defer to a follow-up `chore(*): apply ruff format` plan.
Out of scope for Plan 07-07's gap-closure objective.
