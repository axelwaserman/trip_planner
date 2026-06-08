"""Parametrised mapping table for ``_raise_from_http_status``.

Locks the D-04 mapping contract:

* 401, 422, 4xx → :class:`APIClientError` (retryable=False)
* 429 → :class:`APIRateLimitError` (retryable=True)
* 5xx, unknown → :class:`APIServerError` (retryable=True)

Asserts both the raised type and the retryable flag, plus that ``__cause__``
is the chained upstream exception (so callers can debug the original
:class:`StatusError` without losing the trail). Body content NEVER appears
in messages — see ``test_duffel_client.py`` for that invariant.
"""

import pytest

from app.exceptions import APIClientError, APIError, APIRateLimitError, APIServerError
from app.flights.duffel_client import _raise_from_http_status


@pytest.mark.parametrize(
    ("status", "exc_type", "retryable"),
    [
        (401, APIClientError, False),
        (400, APIClientError, False),
        (404, APIClientError, False),
        (422, APIClientError, False),  # D-04: Duffel validation error.
        (429, APIRateLimitError, True),
        (500, APIServerError, True),
        (503, APIServerError, True),
        (599, APIServerError, True),  # Unknown 5xx — fall-through case.
    ],
)
def test_raise_from_http_status(status: int, exc_type: type[APIError], retryable: bool) -> None:
    cause = RuntimeError("upstream")
    with pytest.raises(exc_type) as exc_info:
        _raise_from_http_status(status, cause)
    assert exc_info.value.retryable is retryable
    assert exc_info.value.__cause__ is cause
