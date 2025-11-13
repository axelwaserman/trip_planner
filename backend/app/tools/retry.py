"""Retry decorator with exponential backoff for async functions."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

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

    Retries the decorated function on specified exceptions with exponential
    backoff. Only retries if the exception has `retryable=True` attribute.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_base: Base for exponential backoff calculation (default: 2.0)
                     Delay = backoff_base ^ attempt
        exceptions: Tuple of exception types to catch and potentially retry

    Returns:
        Decorated async function with retry logic

    Example:
        >>> @retry_on_failure(max_retries=3, backoff_base=2.0)
        ... async def fetch_data():
        ...     return await api_client.get("/data")
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # Check if error is retryable
                    if isinstance(e, APIError) and not e.retryable:
                        logger.warning(f"{func.__name__} failed with non-retryable error: {e}")
                        raise

                    if attempt < max_retries:
                        delay = backoff_base**attempt
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{e}. Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )

            # Raise the last exception after all retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry logic error")

        return wrapper

    return decorator
