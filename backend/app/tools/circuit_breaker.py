"""Async-safe circuit breaker helper for ``pybreaker``.

The ``@cb`` decorator shipped by ``pybreaker`` does NOT trip on async functions
(verified live with pybreaker 1.4.1 — see ``07-RESEARCH.md`` Pitfall 4). It wraps
the synchronously-returned coroutine object and never observes the awaited
exception, so the failure counter stays at 0. This module exposes
:func:`call_with_breaker`, a manual wrapper that drives pybreaker's state-machine
API (``state.before_call`` / ``state._handle_error`` / ``state._handle_success``)
directly so async failures actually count toward ``fail_max``.

Plan 04's ``AmadeusFlightClient.search`` composes this helper with the
:func:`app.tools.retry.retry_on_failure` tenacity wrapper; the breaker caps the
retry storm against a struggling Amadeus endpoint per D-12.
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

import pybreaker

logger = logging.getLogger(__name__)


async def call_with_breaker[T](
    breaker: pybreaker.CircuitBreaker,
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Invoke ``coro_fn`` under ``breaker`` with correct async failure accounting.

    Pybreaker's public ``@breaker`` decorator wraps the coroutine object instead
    of the awaited result, so the failure counter never increments and the
    circuit never trips on async failures. This helper drives the underlying
    state machine directly:

    1. ``breaker.state.before_call(...)`` — synchronously raises
       :class:`pybreaker.CircuitBreakerError` when the circuit is open, before
       the wrapped coroutine is ever scheduled.
    2. ``await coro_fn(*args, **kwargs)`` — the actual work.
    3. On exception classified as a "system error" by
       ``breaker.is_system_error(exc)``, increment the failure counter via
       ``state._handle_error(exc, reraise=False)``. If this is the failure that
       causes the trip, pybreaker (with ``throw_new_error_on_trip=True``) raises
       :class:`pybreaker.CircuitBreakerError` from inside ``_handle_error``,
       masking the original exception — so the trip-causing call surfaces
       ``CircuitBreakerError`` rather than the original error. On non-trip
       failures the original exception is re-raised unchanged.
    4. On success, reset the counter via ``state._handle_success()`` and return
       the awaited value.

    The ``_handle_error`` / ``_handle_success`` accesses are pybreaker
    internals (single-underscore "protected" API); ``pybreaker>=1.4.1,<2.0`` is
    pinned in ``pyproject.toml`` to lock the contract used here. The
    ``# noqa: SLF001`` comments on those lines document the deliberate access.

    See ``07-RESEARCH.md`` Pitfall 4 for the live reproduction of the decorator
    anti-pattern; ``tests/unit/test_circuit_breaker.py`` regression-locks both
    the trip threshold and the decorator anti-pattern.

    Args:
        breaker: Configured :class:`pybreaker.CircuitBreaker` instance. Should
            be created with ``throw_new_error_on_trip=True`` so callers can
            distinguish a tripped circuit from the wrapped coroutine's own
            failures.
        coro_fn: Async callable to invoke under the breaker.
        *args: Positional arguments forwarded to ``coro_fn``.
        **kwargs: Keyword arguments forwarded to ``coro_fn``.

    Returns:
        The awaited result of ``coro_fn(*args, **kwargs)``.

    Raises:
        pybreaker.CircuitBreakerError: If the circuit is open at call time
            (raised synchronously by ``before_call``) or trips on this call
            (raised from ``_handle_error`` when ``throw_new_error_on_trip=True``,
            masking the original exception that caused the trip).
        BaseException: Any non-trip exception raised by ``coro_fn`` is re-raised
            unchanged. System errors (per ``breaker.is_system_error``) also
            increment the failure counter; non-system errors (e.g.
            :class:`KeyboardInterrupt`) propagate without affecting state.
    """
    breaker.state.before_call(coro_fn, *args, **kwargs)
    try:
        result = await coro_fn(*args, **kwargs)
    except BaseException as exc:
        if breaker.is_system_error(exc):
            # noqa: SLF001 — pybreaker internal API; pinned pybreaker<2.0 in pyproject.toml.
            # The public @breaker decorator does not work on async functions (Pitfall 4),
            # so we drive state._handle_error directly to count async failures.
            breaker.state._handle_error(exc, reraise=False)  # noqa: SLF001
        raise
    else:
        breaker.state._handle_success()  # noqa: SLF001 — pybreaker internal; see _handle_error note above.
        return result
