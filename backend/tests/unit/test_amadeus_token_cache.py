"""Tests for ``AmadeusFlightClient`` token cache concurrency + freshness.

These tests regression-lock three invariants of the in-process token cache
defined in :mod:`app.flights.amadeus_client`:

1. **Concurrent-refresh-once (D-01).** When N coroutines call ``_get_token()``
   simultaneously, exactly one underlying ``_refresh_token`` invocation fires
   and all callers observe the same token (``asyncio.Lock`` + double-checked
   locking).
2. **Proactive refresh inside the 60-second buffer.** A token that expires in
   less than 60 seconds is refreshed even though it has not technically
   expired yet (07-RESEARCH.md Pattern 1).
3. **Cached-token short-circuit when fresh.** A token that is well outside
   the buffer is returned without invoking ``_refresh_token``.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pyreqwest.exceptions import StatusError

from app.exceptions import APIClientError, APIError
from app.flights.amadeus_client import AmadeusFlightClient


@pytest.mark.asyncio
async def test_concurrent_callers_refresh_token_once() -> None:
    """5 concurrent ``_get_token()`` callers cause exactly 1 refresh."""
    client = AmadeusFlightClient("k", "s", "https://test.api.amadeus.com")

    refresh_count = 0

    async def fake_refresh() -> str:
        nonlocal refresh_count
        # Yield to the event loop so the lock contention is realistic.
        await asyncio.sleep(0)
        refresh_count += 1
        client._access_token = "fresh-token"
        client._expires_at = datetime.now(UTC) + timedelta(seconds=1800)
        return "fresh-token"

    with patch.object(client, "_refresh_token", side_effect=fake_refresh):
        tokens = await asyncio.gather(*(client._get_token() for _ in range(5)))

    assert refresh_count == 1
    assert tokens == ["fresh-token"] * 5


@pytest.mark.asyncio
async def test_proactive_refresh_within_buffer() -> None:
    """A token expiring in 30s (< 60s buffer) triggers refresh."""
    client = AmadeusFlightClient("k", "s", "https://test.api.amadeus.com")
    client._access_token = "old"
    client._expires_at = datetime.now(UTC) + timedelta(seconds=30)

    refresh_mock = AsyncMock(return_value="new")
    with patch.object(client, "_refresh_token", refresh_mock):
        token = await client._get_token()

    assert token == "new"
    refresh_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_token_returned_when_fresh() -> None:
    """A token expiring in 600s is returned without invoking refresh."""
    client = AmadeusFlightClient("k", "s", "https://test.api.amadeus.com")
    client._access_token = "cached"
    client._expires_at = datetime.now(UTC) + timedelta(seconds=600)

    refresh_mock = AsyncMock(return_value="should-not-be-returned")
    with patch.object(client, "_refresh_token", refresh_mock):
        token = await client._get_token()

    assert token == "cached"
    assert refresh_mock.await_count == 0


# ---------------------------------------------------------------------------
# CR-02 regression tests: _refresh_token HTTP status + malformed-body handling.
#
# Both tests stub the ``ClientBuilder`` chain that ``_refresh_token`` uses
# for its OAuth2 POST. The chain shape is:
#
#   ClientBuilder()
#     .timeout(td)
#     .error_for_status(True)
#     .build()                  -> async context manager (FakeClient)
#       .post(url)              -> FakeRequestBuilder
#         .form({...})          -> self
#         .build()              -> FakeRequest
#           .send()             -> awaitable response (FakeResponse) OR raises
#
# Mirrors the strategy in test_amadeus_client.py::
# test_search_401_invalidates_token_cache; only the chain shape differs.
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Pyreqwest request fake. ``send`` behavior is controlled per-test."""

    def __init__(self, send_impl: object) -> None:
        # ``send_impl`` is an async callable returning a response OR raising.
        self._send_impl = send_impl

    async def send(self) -> object:
        # The fake's behavior is delegated so each test can wire either an
        # exception path or a response path without subclassing.
        return await self._send_impl()  # type: ignore[operator]


class _FakeRequestBuilder:
    def __init__(self, send_impl: object) -> None:
        self._send_impl = send_impl

    def form(self, _payload: dict[str, str]) -> "_FakeRequestBuilder":
        return self

    def build(self) -> _FakeRequest:
        return _FakeRequest(self._send_impl)


class _FakeClient:
    def __init__(self, send_impl: object) -> None:
        self._send_impl = send_impl

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def post(self, _url: str) -> _FakeRequestBuilder:
        return _FakeRequestBuilder(self._send_impl)


def _wire_client_builder(cb_cls: object, send_impl: object) -> None:
    """Wire ``cb_cls`` (the patched ClientBuilder class) to yield FakeClient."""
    client_builder = cb_cls.return_value  # type: ignore[attr-defined]
    client_builder.timeout.return_value = client_builder
    client_builder.error_for_status.return_value = client_builder
    client_builder.build.return_value = _FakeClient(send_impl)


@pytest.mark.asyncio
async def test_refresh_token_401_raises_apiclient_error_not_retryable() -> None:
    """A 401 from the OAuth POST surfaces as APIClientError(retryable=False) (D-11 / CR-02).

    Pre-fix, the 401 body lacked ``access_token`` and the resulting
    ``KeyError`` was caught by the catch-all and wrapped as
    ``APIError(retryable=True)`` — tenacity then retried 3× against bad
    credentials (T-07-04). Post-fix, ``error_for_status(True)`` makes
    pyreqwest raise ``StatusError`` and the explicit branch routes through
    ``_raise_from_http_status`` → ``APIClientError(retryable=False)``.
    """
    client = AmadeusFlightClient("k", "s", "https://test.api.amadeus.com")
    fake_status = StatusError("auth failed", {"status": 401, "causes": []})

    async def fake_send_401() -> object:
        raise fake_status

    with patch("app.flights.amadeus_client.ClientBuilder") as cb_cls:
        _wire_client_builder(cb_cls, fake_send_401)

        with pytest.raises(APIClientError) as exc_info:
            await client._refresh_token()

    assert exc_info.value.retryable is False
    # Refresh failed before any cache write; the slot stays unset.
    assert client._access_token is None


@pytest.mark.asyncio
async def test_refresh_token_malformed_body_raises_non_retryable() -> None:
    """A 2xx response missing access_token / expires_in is non-retryable (CR-02).

    Vendor protocol violation, not transient. Pre-fix, ``body["access_token"]``
    raised ``KeyError`` which the catch-all wrapped as
    ``APIError(retryable=True)`` — making tenacity retry three times against
    a misbehaving Amadeus deploy. Post-fix, the focused malformed-body guard
    surfaces ``APIError(retryable=False)`` with a helpful static message.
    """
    client = AmadeusFlightClient("k", "s", "https://test.api.amadeus.com")

    class _FakeResponse:
        async def json(self) -> dict[str, str]:
            return {"unexpected": "shape"}

    async def fake_send_ok() -> object:
        return _FakeResponse()

    with patch("app.flights.amadeus_client.ClientBuilder") as cb_cls:
        _wire_client_builder(cb_cls, fake_send_ok)

        with pytest.raises(APIError) as exc_info:
            await client._refresh_token()

    assert exc_info.value.retryable is False
    assert "malformed" in exc_info.value.message.lower()
    # Cache slot stays unset on contract violation.
    assert client._access_token is None
