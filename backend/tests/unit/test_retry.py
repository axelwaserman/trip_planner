"""Tests for retry decorator."""

import asyncio

import pytest

from app.exceptions import APIClientError, APIServerError, APITimeoutError
from app.utils.retry import retry_on_failure


# Test helper functions
async def successful_function() -> str:
    """Function that succeeds immediately."""
    return "success"


async def failing_function(fail_count: int) -> str:
    """Function that fails a specific number of times then succeeds.

    Args:
        fail_count: Number of times to fail before succeeding
    """
    if not hasattr(failing_function, "attempts"):
        failing_function.attempts = 0  # type: ignore[attr-defined]

    failing_function.attempts += 1  # type: ignore[attr-defined]

    if failing_function.attempts <= fail_count:  # type: ignore[attr-defined]
        raise APITimeoutError(message="Temporary failure")

    return "success"


async def always_failing_function() -> str:
    """Function that always fails."""
    raise APIServerError(message="Always fails")


async def non_retryable_error_function() -> str:
    """Function that raises non-retryable error."""
    raise APIClientError(message="Bad request")


@pytest.fixture(autouse=True)
def reset_function_state() -> None:
    """Reset function call counter between tests."""
    if hasattr(failing_function, "attempts"):
        delattr(failing_function, "attempts")


@pytest.mark.asyncio
async def test_retry_successful_function() -> None:
    """Test retry decorator on function that succeeds immediately."""
    decorated = retry_on_failure(max_retries=3)(successful_function)
    result = await decorated()
    assert result == "success"


@pytest.mark.asyncio
async def test_retry_eventually_succeeds() -> None:
    """Test retry decorator retries and eventually succeeds."""

    @retry_on_failure(max_retries=3, backoff_base=0.01)
    async def func() -> str:
        return await failing_function(fail_count=2)

    result = await func()
    assert result == "success"
    assert failing_function.attempts == 3  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_retry_exhausts_attempts() -> None:
    """Test retry decorator exhausts all attempts and raises exception."""

    @retry_on_failure(max_retries=2, backoff_base=0.01)
    async def func() -> str:
        return await always_failing_function()

    with pytest.raises(APIServerError, match="Always fails"):
        await func()


@pytest.mark.asyncio
async def test_retry_non_retryable_error() -> None:
    """Test retry decorator doesn't retry non-retryable errors."""

    @retry_on_failure(max_retries=3, backoff_base=0.01)
    async def func() -> str:
        return await non_retryable_error_function()

    # Should fail immediately without retries
    with pytest.raises(APIClientError, match="Bad request"):
        await func()


@pytest.mark.asyncio
async def test_retry_exponential_backoff() -> None:
    """Test retry decorator applies exponential backoff."""
    call_times: list[float] = []

    @retry_on_failure(max_retries=3, backoff_base=0.1)
    async def func() -> str:
        call_times.append(asyncio.get_event_loop().time())
        if len(call_times) <= 3:
            raise APITimeoutError(message="Timeout")
        return "success"

    result = await func()
    assert result == "success"
    assert len(call_times) == 4  # Initial + 3 retries

    # Check backoff delays (approximately 0.1^0=1, 0.1^1=0.1, 0.1^2=0.01)
    # We use 0.1 as backoff_base for faster tests
    # Allow some tolerance for timing
    if len(call_times) >= 2:
        delay1 = call_times[1] - call_times[0]
        assert delay1 >= 0.09  # backoff_base^0 = 1, but we use 0.1 for test speed


@pytest.mark.asyncio
async def test_retry_custom_exceptions() -> None:
    """Test retry decorator with custom exception list."""

    class CustomError(Exception):
        retryable = True

    @retry_on_failure(max_retries=2, backoff_base=0.01, exceptions=(CustomError,))
    async def func() -> str:
        raise CustomError("Custom error")

    with pytest.raises(CustomError):
        await func()


@pytest.mark.asyncio
async def test_retry_preserves_function_metadata() -> None:
    """Test retry decorator preserves original function metadata."""

    @retry_on_failure(max_retries=3)
    async def documented_function() -> str:
        """This function has documentation."""
        return "success"

    assert documented_function.__name__ == "documented_function"
    assert documented_function.__doc__ == "This function has documentation."


@pytest.mark.asyncio
async def test_retry_with_zero_retries() -> None:
    """Test retry decorator with max_retries=0 (no retries)."""

    @retry_on_failure(max_retries=0, backoff_base=0.01)
    async def func() -> str:
        raise APITimeoutError(message="Immediate failure")

    with pytest.raises(APITimeoutError):
        await func()


@pytest.mark.asyncio
async def test_retry_passes_args_and_kwargs() -> None:
    """Test retry decorator preserves function arguments."""

    @retry_on_failure(max_retries=2, backoff_base=0.01)
    async def func_with_args(a: int, b: str, c: bool = False) -> str:
        return f"{a}-{b}-{c}"

    result = await func_with_args(42, "test", c=True)
    assert result == "42-test-True"
