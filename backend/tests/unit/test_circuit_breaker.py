"""Tests for the async-safe ``call_with_breaker`` helper.

These tests regression-lock four invariants of ``app.tools.circuit_breaker``:

1. After ``fail_max`` consecutive system-error failures, the breaker trips and
   raises :class:`pybreaker.CircuitBreakerError` instead of the wrapped
   coroutine's own exception.
2. A successful call resets the failure counter, so alternating
   success/failure stays under ``fail_max``.
3. Pybreaker's ``@breaker`` decorator on an async function does NOT trip the
   circuit (07-RESEARCH.md Pitfall 4) — this test documents that anti-pattern
   so future contributors don't reach for it.
4. On non-trip failures, the original exception type and message survive the
   wrapper (no wrapping in ``CircuitBreakerError``).
"""

import pybreaker
import pytest

from app.tools.circuit_breaker import call_with_breaker


@pytest.mark.asyncio
async def test_breaker_trips_after_fail_max() -> None:
    """After ``fail_max`` system-error failures, the breaker trips.

    Note on pybreaker semantics with ``throw_new_error_on_trip=True``: the call
    that *causes* the trip raises :class:`pybreaker.CircuitBreakerError` from
    inside ``state._handle_error`` (pybreaker masks the original exception on
    the trip-causing call). With ``fail_max=3`` we therefore expect:

    * calls 1–2: ``RuntimeError`` propagates unchanged, breaker stays closed
    * call 3: trips, raises ``CircuitBreakerError`` (NOT the wrapped
      ``RuntimeError`` — the trip masks it)
    """
    breaker = pybreaker.CircuitBreaker(
        fail_max=3,
        reset_timeout=60,
        throw_new_error_on_trip=True,
    )

    async def always_fails() -> None:
        raise RuntimeError("boom")

    # First fail_max-1 calls re-raise the wrapped exception unchanged.
    for _ in range(2):
        with pytest.raises(RuntimeError, match="boom"):
            await call_with_breaker(breaker, always_fails)

    assert breaker.current_state == "closed"

    # The fail_max-th failure trips the circuit; pybreaker raises
    # CircuitBreakerError from _handle_error, masking the RuntimeError.
    with pytest.raises(pybreaker.CircuitBreakerError):
        await call_with_breaker(breaker, always_fails)

    assert breaker.current_state == "open"

    # Once open, before_call short-circuits subsequent calls without invoking
    # the wrapped coroutine at all.
    with pytest.raises(pybreaker.CircuitBreakerError):
        await call_with_breaker(breaker, always_fails)


@pytest.mark.asyncio
async def test_breaker_success_resets_counter() -> None:
    """A success between failures resets the counter, keeping the breaker closed."""
    breaker = pybreaker.CircuitBreaker(
        fail_max=2,
        reset_timeout=60,
        throw_new_error_on_trip=True,
    )

    async def always_fails() -> None:
        raise RuntimeError("boom")

    async def succeeds() -> str:
        return "ok"

    # fail (counter -> 1)
    with pytest.raises(RuntimeError):
        await call_with_breaker(breaker, always_fails)

    # success (counter -> 0)
    result = await call_with_breaker(breaker, succeeds)
    assert result == "ok"

    # fail again (counter -> 1, NOT 2 — would trip if counter hadn't been reset)
    with pytest.raises(RuntimeError):
        await call_with_breaker(breaker, always_fails)

    assert breaker.current_state == "closed"


@pytest.mark.asyncio
async def test_breaker_decorator_on_async_does_not_trip() -> None:
    """Regression-lock for 07-RESEARCH.md Pitfall 4.

    Pybreaker's ``@breaker`` decorator wraps the synchronously-returned
    coroutine object, so the awaited exception never reaches the failure
    counter. Calling the decorated coroutine ``fail_max + 3`` times produces
    NO trip — ``current_state`` remains ``"closed"``.

    DO NOT use ``@breaker`` on async functions. Always use
    :func:`app.tools.circuit_breaker.call_with_breaker` instead.
    """
    breaker = pybreaker.CircuitBreaker(
        fail_max=2,
        reset_timeout=60,
        throw_new_error_on_trip=True,
    )

    @breaker  # ANTI-PATTERN — documented here as a regression guard, see docstring.
    async def broken() -> None:
        raise RuntimeError("x")

    # Call fail_max + 3 times. None of these failures count toward the breaker
    # because the decorator's sync wrapper never sees the awaited exception.
    for _ in range(5):
        with pytest.raises(RuntimeError):
            await broken()

    assert breaker.current_state == "closed"
    assert breaker.fail_counter == 0


@pytest.mark.asyncio
async def test_call_with_breaker_propagates_original_exception() -> None:
    """Non-trip failures re-raise the original exception type and message intact."""
    # fail_max=10 so we don't trip during this test; the 1st failure must not
    # be masked by CircuitBreakerError.
    breaker = pybreaker.CircuitBreaker(
        fail_max=10,
        reset_timeout=60,
        throw_new_error_on_trip=True,
    )

    async def fails() -> None:
        raise ValueError("specific")

    with pytest.raises(ValueError, match="specific"):
        await call_with_breaker(breaker, fails)

    # The breaker counted the failure but didn't trip.
    assert breaker.current_state == "closed"
    assert breaker.fail_counter == 1
