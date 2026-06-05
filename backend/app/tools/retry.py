"""Retry decorator with exponential backoff for async functions.

Thin wrapper over `tenacity` (D-10 from phase 07-real-flight-api): the project-wide
retry primitive is implemented via `tenacity.retry` rather than a hand-rolled
sleep loop. The public signature of :func:`retry_on_failure` is preserved
bit-for-bit so every existing call site keeps working.

Key invariants (regression-locked by ``tests/unit/test_retry.py``):

* The decorator only retries when the raised exception is an instance of one of
  the configured ``exceptions`` AND has ``retryable=True`` — non-retryable
  ``APIError`` subclasses raise immediately on the first attempt.
* ``reraise=True`` is mandatory: after all retries are exhausted, the ORIGINAL
  ``APIError`` subclass surfaces to callers — never ``tenacity.RetryError``.
  This preserves the ``APIError`` hierarchy and the ``retryable`` flag semantics
  upstream code depends on (Pitfall 5 in 07-RESEARCH.md).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.exceptions import APIError

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


def retry_on_failure(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (APIError,),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry decorator with exponential backoff for async functions.

    Implemented via ``tenacity.retry``: the decorated coroutine is retried while
    the raised exception matches ``exceptions`` AND has ``retryable=True``.
    Non-retryable errors (e.g. ``APIClientError(retryable=False)``) raise on the
    first attempt without sleeping.

    Args:
        max_retries: Maximum number of retry attempts after the initial call
            (default: 3). The decorator therefore makes up to
            ``max_retries + 1`` total attempts.
        backoff_base: Multiplier passed to :func:`tenacity.wait_exponential`;
            the wait between attempts ``n`` and ``n+1`` is
            ``backoff_base * 2^(n-1)`` seconds (default: 2.0).
        exceptions: Tuple of exception types eligible for retry. Defaults to
            ``(APIError,)``. An exception only triggers a retry if it is an
            instance of one of these types AND its ``retryable`` attribute is
            truthy.

    Returns:
        A decorator that wraps an async function with the retry policy. After
        all retries are exhausted, the original exception is raised — not
        ``tenacity.RetryError`` (the ``reraise=True`` invariant).

    Example:
        >>> @retry_on_failure(max_retries=3, backoff_base=2.0)
        ... async def fetch_data() -> dict[str, str]:
        ...     return await api_client.get("/data")
    """

    def _is_retryable(exc: BaseException) -> bool:
        # Mirrors the hand-rolled implementation's predicate exactly: an exception
        # must be one of the configured types AND carry retryable=True.
        return isinstance(exc, exceptions) and getattr(exc, "retryable", False)

    return retry(
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(multiplier=backoff_base),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
