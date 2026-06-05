"""Parametrized HTTP-status -> APIError-subclass mapping (D-11).

Locks the contract of :func:`app.flights.amadeus_client._raise_from_http_status`
across the full status code matrix used by Amadeus:

* 401 / non-429 4xx -> :class:`APIClientError(retryable=False)`
* 429 -> :class:`APIRateLimitError(retryable=True)`
* 5xx -> :class:`APIServerError(retryable=True)`
"""

import pytest

from app.exceptions import APIClientError, APIError, APIRateLimitError, APIServerError
from app.flights.amadeus_client import _raise_from_http_status


@pytest.mark.parametrize(
    ("status", "exc_type", "retryable"),
    [
        (401, APIClientError, False),
        (400, APIClientError, False),
        (404, APIClientError, False),
        (429, APIRateLimitError, True),
        (500, APIServerError, True),
        (503, APIServerError, True),
    ],
)
def test_raise_from_http_status(
    status: int, exc_type: type[APIError], retryable: bool
) -> None:
    """Each HTTP status maps to the correct APIError subclass + retryable flag."""
    cause = RuntimeError("upstream")
    with pytest.raises(exc_type) as exc_info:
        _raise_from_http_status(status, cause)

    assert exc_info.value.retryable is retryable
    # Ensure the original cause survives via __cause__ — important for
    # debugging: the wrapped pyreqwest StatusError should remain reachable.
    assert exc_info.value.__cause__ is cause
