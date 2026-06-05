---
phase: 07-real-flight-api
plan: 03
subsystem: infra
tags: [pybreaker, circuit-breaker, async, resilience, tenacity, python-3.13]

requires:
  - phase: 07-real-flight-api
    provides: Plan 01 — `retry_on_failure` tenacity wrapper (`backend/app/tools/retry.py`)
provides:
  - Async-safe `call_with_breaker(breaker, coro_fn, *args, **kwargs)` helper in `backend/app/tools/circuit_breaker.py`
  - Pinned `pybreaker>=1.4.1,<2.0` dependency with inline rationale in `backend/pyproject.toml`
  - 4-test regression lock for trip threshold + decorator anti-pattern + counter reset + exception propagation
affects: [07-real-flight-api Plan 04 (AmadeusFlightClient.search composes call_with_breaker with retry_on_failure)]

tech-stack:
  added: [pybreaker>=1.4.1,<2.0]
  patterns:
    - "Async-safe circuit breaker wrapper around pybreaker state machine API (state.before_call / state._handle_error / state._handle_success) — the @breaker decorator does NOT trip on async functions (07-RESEARCH.md Pitfall 4, regression-locked)"
    - "PEP 695 type-parameter syntax (`async def call_with_breaker[T](...)`) for async generic helpers — required by ruff UP047 on Python 3.13"
    - "Inline `# noqa: SLF001` with rationale comment for deliberate single-underscore protected-API access; pin upper-bound on the dependency to lock the contract"

key-files:
  created:
    - backend/app/tools/circuit_breaker.py
    - backend/tests/unit/test_circuit_breaker.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock

key-decisions:
  - "Pin pybreaker<2.0 (not just >=1.4.1) because call_with_breaker accesses state._handle_error and state._handle_success — single-underscore protected APIs that may break across major versions. Rationale is captured inline in pyproject.toml."
  - "Use PEP 695 type parameters (`async def call_with_breaker[T](...)`) instead of `TypeVar('T')` — ruff UP047 mandates the modern syntax on Python 3.13, and it keeps the helper aligned with the project's `requires-python = '>=3.13'` floor."
  - "test_breaker_trips_after_fail_max uses fail_max=3 (not the plan's fail_max=2) so it can exercise both behaviors in one test: fail_max-1 calls re-raise the wrapped RuntimeError, then the trip-causing call surfaces CircuitBreakerError. With fail_max=2 the very first failure-loop iteration would already trip and mask the RuntimeError, defeating the purpose of having a separate 'before' phase."

patterns-established:
  - "Async helpers that cap third-party retry/breaker storms compose at the call site (`call_with_breaker(breaker, retry_on_failure_decorated_fn, *args)`) rather than via stacked decorators — mandatory because pybreaker's @breaker is broken on async."
  - "Tests for third-party-library wrappers include a 'documented anti-pattern' regression test (e.g. `test_breaker_decorator_on_async_does_not_trip`) so future contributors can see WHY the wrapper exists and don't reach for the broken upstream pattern."

requirements-completed: [REQ-real-flight-api]

duration: 14min
completed: 2026-06-05
---

# Phase 07 Plan 03: Async-safe pybreaker helper Summary

**Async-safe `call_with_breaker` wrapper around pybreaker's state machine, with regression tests locking the trip threshold + the @decorator anti-pattern (07-RESEARCH Pitfall 4); pybreaker pinned `>=1.4.1,<2.0` for the protected-API contract.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-05T05:54:00Z
- **Completed:** 2026-06-05T06:08:00Z
- **Tasks:** 2
- **Files created:** 2 (`backend/app/tools/circuit_breaker.py`, `backend/tests/unit/test_circuit_breaker.py`)
- **Files modified:** 2 (`backend/pyproject.toml`, `backend/uv.lock`)

## Accomplishments

- New module `backend/app/tools/circuit_breaker.py` exporting `call_with_breaker(breaker, coro_fn, *args, **kwargs) -> T` — the async-safe wrapper Plan 04's `AmadeusFlightClient.search` will compose with `retry_on_failure` (Plan 01).
- Module drives pybreaker's state machine directly (`state.before_call` / `state._handle_error` / `state._handle_success`) because the public `@breaker` decorator wraps the synchronously-returned coroutine and never observes the awaited exception (verified live with pybreaker 1.4.1; see 07-RESEARCH.md Pitfall 4).
- 4 regression-locked tests in `backend/tests/unit/test_circuit_breaker.py`:
  1. `test_breaker_trips_after_fail_max` — `fail_max=3` proves the first 2 failures re-raise `RuntimeError`, the 3rd failure trips and surfaces `CircuitBreakerError`, and subsequent calls short-circuit via `before_call`.
  2. `test_breaker_success_resets_counter` — alternating fail/success/fail keeps the breaker closed because `_handle_success` resets the counter.
  3. `test_breaker_decorator_on_async_does_not_trip` — calling a `@breaker`-decorated async coroutine `fail_max + 3` times produces NO trip; `current_state` stays `"closed"` and `fail_counter == 0`. This is the regression lock for Pitfall 4.
  4. `test_call_with_breaker_propagates_original_exception` — with `fail_max=10` (no risk of trip), a wrapped `ValueError("specific")` surfaces with type and message intact.
- `pybreaker>=1.4.1,<2.0` added to `backend/pyproject.toml` with an inline rationale comment explaining the pin (D-12 / RESEARCH Pattern 3 / protected-API access).
- Full unit suite (273 tests) green; mypy strict clean; ruff clean.

## Task Commits

1. **Task 1: Add pybreaker dep + create call_with_breaker helper module** — `ab10c68` (feat)
2. **Task 2: Add tests for fail_max trip + decorator anti-pattern regression** — `aaa9e48` (test)

**Plan metadata commit:** _appended below as docs commit_

## Files Created/Modified

- `backend/app/tools/circuit_breaker.py` (new) — Async-safe `call_with_breaker` helper. Module docstring + function docstring document Pitfall 4 and pybreaker's actual trip semantics with `throw_new_error_on_trip=True`.
- `backend/tests/unit/test_circuit_breaker.py` (new) — 4-test regression lock.
- `backend/pyproject.toml` — Added `pybreaker>=1.4.1,<2.0` with inline rationale comment (lines 30–32).
- `backend/uv.lock` — Lockfile sync from `uv add`.

## Decisions Made

- **PEP 695 type parameters over `TypeVar`:** Ruff `UP047` flagged `T = TypeVar("T")` + `async def call_with_breaker(...) -> T`. Switched to `async def call_with_breaker[T](...) -> T`. Project floor is Python 3.13, so the modern syntax is the appropriate choice and matches the lint configuration.
- **`# noqa: SLF001` text:** The exact suppression comments used are:
  - On `state._handle_error`: `# noqa: SLF001` with a 3-line rationale block above the call: _"pybreaker internal API; pinned pybreaker<2.0 in pyproject.toml. The public @breaker decorator does not work on async functions (Pitfall 4), so we drive state._handle_error directly to count async failures."_
  - On `state._handle_success`: `# noqa: SLF001 — pybreaker internal; see _handle_error note above.`
- **No `# type: ignore` was needed** on `state.before_call` / `state._handle_error` / `state._handle_success` — mypy strict accepted the calls without complaints once the function signature used PEP 695 type parameters. Plan output asked whether `type: ignore` was needed; the answer is **no, none were required.**
- **`pybreaker<2.0` upper-bound** is recorded inline in `pyproject.toml` lines 30–32 with the rationale: "Phase 7 — D-12 (circuit breaker). Pinned <2.0 because call_with_breaker accesses state._handle_error (single-underscore 'protected' API) per RESEARCH Pattern 3."

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Plan's verify command + test would not have produced the documented behavior with `fail_max=2`**

- **Found during:** Task 1 verify (running the plan's inline async smoke test) and reading Task 2's test specification.
- **Issue:** Pybreaker 1.4.1 with `throw_new_error_on_trip=True` raises `CircuitBreakerError` from inside `state._handle_error` on the failure that *causes* the trip — masking the wrapped exception. The plan's verify command and `test_breaker_trips_after_fail_max` both assumed `fail_max=2` would allow 2 `RuntimeError`-propagating calls and then a 3rd call would raise `CircuitBreakerError`. In reality, with `fail_max=2`, the 2nd call raises `CircuitBreakerError` directly. The plan's verify script crashes on iteration 2 (uncaught `CircuitBreakerError`), and the test would fail because iteration 2 of the loop expects `RuntimeError`.
- **Fix:** Adjusted `test_breaker_trips_after_fail_max` to use `fail_max=3` so it exercises both behaviors in one test (2 RuntimeError calls + 1 trip-causing CircuitBreakerError call). Updated the docstring of `call_with_breaker` to document this real pybreaker behavior (the trip-causing call masks the original exception). The Task 1 verify smoke test was also re-run with `fail_max=3` and printed `TRIPPED` as expected.
- **Files modified:** `backend/app/tools/circuit_breaker.py` (docstring), `backend/tests/unit/test_circuit_breaker.py` (`fail_max=3` instead of 2).
- **Verification:** Empirical pybreaker probe (script printed: call 1 → RuntimeError, call 2 → CircuitBreakerError with state=open, calls 3-5 → CircuitBreakerError "Timeout not elapsed"). All 4 tests pass.
- **Committed in:** `ab10c68` (Task 1, docstring) and `aaa9e48` (Task 2, test logic).

**2. [Rule 3 — Blocking] Ruff `UP047` blocked the original `TypeVar("T")` signature**

- **Found during:** Task 1 (`uv run ruff check app/tools/circuit_breaker.py`).
- **Issue:** Ruff requires PEP 695 type-parameter syntax on Python 3.13 (`UP047`), but the plan/PATTERNS code template uses `TypeVar("T")` + `Callable[..., Coroutine[Any, Any, T]]` + `-> T`. The original signature failed lint.
- **Fix:** Removed the module-level `T = TypeVar("T")` and the `TypeVar` import, switched to `async def call_with_breaker[T](...) -> T`. The `T` symbol stays in scope inside the function body via the type-parameter list.
- **Files modified:** `backend/app/tools/circuit_breaker.py` (imports + function signature).
- **Verification:** Ruff + mypy strict both pass.
- **Committed in:** `ab10c68` (Task 1).

---

**Total deviations:** 2 auto-fixed (1 bug in plan-spec correctness against actual pybreaker semantics, 1 blocking lint rule).
**Impact on plan:** Both fixes essential. The fail_max adjustment is a Rule 1 correctness fix — the plan's behavior contract was inaccurate against the real library. The `UP047` adjustment is a Rule 3 blocking lint fix that aligns with the project's Python 3.13 floor. No scope creep; same files, same exports, same test coverage as planned.

## Issues Encountered

- pybreaker 1.4.1's behavior with `throw_new_error_on_trip=True` was clarified empirically (see deviation #1). The library's `_handle_error(exc, reraise=False)` does not mean "do not raise anything" — it means "do not raise the *wrapped* exception via on_failure"; `on_failure` itself still raises `CircuitBreakerError` when the trip threshold is reached. This is now documented in the module's docstring.

## User Setup Required

None — `pybreaker` is a pure-Python dependency installed via `uv add` and locked in `uv.lock`. No environment variables, no external services, no manual configuration.

## Next Phase Readiness

- **Plan 04 unblocked:** `AmadeusFlightClient.search` can now compose `@retry_on_failure` (Plan 01) with `call_with_breaker(self._breaker, self._search_impl, query, ...)` per PATTERNS lines 130-145.
- **Async-safety invariant locked:** Future contributors who try `@breaker` on an async coroutine will see `test_breaker_decorator_on_async_does_not_trip` fail or be guided to `call_with_breaker` by its docstring.
- **No blockers carried into the next plan.**

## Self-Check

- `backend/app/tools/circuit_breaker.py`: FOUND (96 lines)
- `backend/tests/unit/test_circuit_breaker.py`: FOUND (4 tests, all passing)
- `backend/pyproject.toml`: FOUND with `pybreaker>=1.4.1,<2.0` pin and rationale comment
- Commit `ab10c68`: FOUND in `git log`
- Commit `aaa9e48`: FOUND in `git log`

## Self-Check: PASSED

---
*Phase: 07-real-flight-api*
*Completed: 2026-06-05*
