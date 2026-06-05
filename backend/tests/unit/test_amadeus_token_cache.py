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
