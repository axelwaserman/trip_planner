---
phase: 07-real-flight-api
reviewed: 2026-06-05T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - .github/workflows/ci.yml
  - backend/app/api/main.py
  - backend/app/api/routes/routes.py
  - backend/app/config.py
  - backend/app/flights/amadeus_client.py
  - backend/app/tools/circuit_breaker.py
  - backend/app/tools/flight_search.py
  - backend/app/tools/retry.py
  - backend/pyproject.toml
  - backend/tests/e2e_amadeus/__init__.py
  - backend/tests/e2e_amadeus/conftest.py
  - backend/tests/e2e_amadeus/test_amadeus_client.py
  - backend/tests/integration/test_auth_routes.py
  - backend/tests/integration/test_health.py
  - backend/tests/integration/test_lifespan_flight_provider.py
  - backend/tests/unit/test_amadeus_client.py
  - backend/tests/unit/test_amadeus_error_mapping.py
  - backend/tests/unit/test_amadeus_token_cache.py
  - backend/tests/unit/test_circuit_breaker.py
  - backend/tests/unit/test_config.py
  - backend/tests/unit/test_retry.py
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-05
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

The Phase 7 Amadeus integration is well-structured and security-conscious overall — Literal narrowing on `amadeus_env`, `SecretStr` wrapping, deliberate omission of `str(exc)` from error messages, an explicit async-safe circuit-breaker helper, and thorough unit coverage of the token cache, retry, and breaker invariants. However, the search composition has a real correctness bug (a double-applied offset), and the `_refresh_token` path lacks the HTTP-status guard that the rest of the client documents — both surface as user-visible defects under the live Amadeus API. Several other warnings cover error-handling fragility, an unused-flag mismatch with what the docstring claims, and test isolation hazards.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `search()` double-applies `offset`, dropping correct results

**File:** `backend/app/flights/amadeus_client.py:331-334`
**Issue:** `_search_impl` ignores `offset` (correct — Amadeus has no native offset), but `search()` then *both* relies on `_search_impl` returning the head of the result set *and* slices `flights[offset : offset + limit]`. Because `_fetch_with_retry_breaker` only returns up to `limit` flights (Amadeus `max=str(limit)` at line 394), the post-fetch slice `flights[offset : offset + limit]` will silently return an empty list (or a truncated tail) for any non-zero `offset`. Worse: even on `offset=0` the slice is fine, but as soon as a caller paginates with `offset > 0`, they get the wrong page (the first `offset` flights of the only fetched page disappear, but no further page is fetched).

The two layers do not compose: either `_search_impl` must request `max=limit+offset` flights and the slice stays, or the slice must drop. As written, paginated callers get incorrect data.

**Fix:**
```python
# Option A — request enough rows so the slice is meaningful:
params["max"] = str(limit + offset)

# Option B — drop the slice; the client returns up to `limit` rows starting at index 0:
async def search(...):
    flights = await self._fetch_with_retry_breaker(query, limit, offset)
    flights = _apply_filters(flights, max_price, max_duration, max_stops)
    flights = _sort_flights(flights, sort_by)
    return flights[:limit]  # offset removed; callers do their own paging
```
Pick one consistently and add a unit test that drives `search(..., limit=2, offset=2)` against a stubbed `_search_impl` returning four results. The current test suite has no `offset > 0` regression lock, which is how this slipped past.

### CR-02: `_refresh_token` blindly indexes JSON body — non-200 responses raise `KeyError` mapped to `APIError(retryable=True)`, hiding 401/4xx as "transient"

**File:** `backend/app/flights/amadeus_client.py:246-274`
**Issue:** `_refresh_token` does NOT call `error_for_status(True)` on the OAuth POST and does NOT branch on the response status. On a real 401 (bad credentials), Amadeus returns a JSON body like `{"error": "invalid_client", ...}` with no `access_token` field. The line `access_token: str = body["access_token"]` then raises `KeyError("access_token")`, which is caught by the broad `except Exception` and re-wrapped as `APIError(message="Amadeus token refresh failed: KeyError", retryable=True)`.

`retryable=True` means tenacity will retry up to 3 more times against the same bad credentials — burning rate-limit budget and (worse) risking account lockout. The contract documented in `_raise_from_http_status` says 401 → `APIClientError(retryable=False)`, but the token-refresh path bypasses that mapping entirely.

The e2e test `test_error_mapping_401_with_bad_credentials` even encodes this defect as the expected behaviour ("401 surfaces from `_refresh_token` as `APIError(retryable=True)` per the catch-all wrap"), which means the regression-lock is locking the bug in place.

**Fix:**
```python
# In _refresh_token:
async with ClientBuilder().timeout(timedelta(seconds=10)).error_for_status(True).build() as client:
    try:
        resp = await client.post(token_url).form({...}).build().send()
        body = await resp.json()
    except StatusError as exc:
        status = int(exc.details.get("status", 0))
        # 401 here means bad creds — non-retryable, mirrors _raise_from_http_status:
        _raise_from_http_status(status, exc)
    except (RequestTimeoutError, ConnectError) as exc:
        raise APIError(message=f"Amadeus token refresh failed: {type(exc).__name__}", retryable=True) from exc

if "access_token" not in body or "expires_in" not in body:
    raise APIError(message="Amadeus token refresh returned malformed body", retryable=False)
```
And update `test_error_mapping_401_with_bad_credentials` to assert `APIClientError`, not generic `APIError`.

## Warnings

### WR-01: Direct `chat_service._metadata` access in routes leaks private state across the architectural boundary

**File:** `backend/app/api/routes/routes.py:109-110, 201-202, 211, 383-388, 414-415`
**Issue:** Five route handlers reach into `chat_service._metadata` (single-underscore "private" attribute) for ownership checks, last-tool-invocation lookup, and post-create metadata read. This is the same anti-pattern that `circuit_breaker.py` calls out and apologizes for (with a `noqa: SLF001` comment) — but here there's no `noqa` and the access pattern is a public route invariant rather than an internal pybreaker pinning. It also means a future refactor of `_metadata` (e.g. moving session metadata into `ConversationRepository`) silently breaks every route. The chat package should expose a typed `await chat_service.get_session_metadata(conversation_id)` (or similar) and the routes call that.

**Fix:** Add a small public method on `ChatService`:
```python
async def get_metadata(self, conversation_id: str) -> dict | None:
    return self._metadata.get(conversation_id)
```
Then routes call `metadata = await chat_service.get_metadata(request.conversation_id)`. Out of scope to fix in Phase 7 if not regressed, but the Phase 7 routes file was modified (per file list) — flag for the next refactor.

### WR-02: `search_flights` validates `max_price > 0` but `max_price == 0` is also valid input — and the error message is wrong

**File:** `backend/app/tools/flight_search.py:399-400`
**Issue:** `if max_price is not None and max_price <= 0:` rejects `max_price=0`, but a user filtering for "free flights" (or a buggy LLM passing 0) gets `"Error: max_price must be a positive number."` — actually `max_price=0` should yield "no flights" naturally via the `_apply_filters` predicate. More importantly, the error string says "positive number" (i.e. `> 0`), which matches the predicate but fights the lower-bound consistency: `passengers >= 1`, `limit >= 1`, `max_stops >= 0`, `max_duration >= 0` — only `max_price` requires `> 0`. Pick one. If you genuinely want to disallow zero, the message should say "must be greater than zero".

**Fix:** Change to `if max_price is not None and max_price < 0:` (or update the error string). The downstream `Decimal(str(max_price))` and `_apply_filters` both handle 0 correctly.

### WR-03: `_extract_carrier_iata` falls back to "ZZ" silently — fallback is invisible to callers and to tests

**File:** `backend/app/tools/flight_search.py:49-64`
**Issue:** When a flight number doesn't start with two uppercase letters, `_extract_carrier_iata` returns `"ZZ"` (an unallocated IATA prefix) without logging. The downstream `FlightSearchResult` then carries `iata_code="ZZ"` and the original `name=flight.carrier`, which renders as a confusing UI ("Carrier: Delta, code: ZZ") and silently drops a real diagnostic signal. At minimum log a warning so the problem is observable in production. Compare with `_extract_booking_class` (amadeus_client.py:528-530), which correctly emits `logger.warning` on the fallback path.

**Fix:**
```python
m = re.match(r"^([A-Z]{2})", flight.flight_number)
if m:
    return m.group(1)
logger.warning("Could not extract IATA carrier from flight_number=%r; falling back to 'ZZ'", flight.flight_number)
return "ZZ"
```

### WR-04: Token cache slow-path holds the lock across the network call — single-flight is correct, but cancellation leaves cache inconsistent

**File:** `backend/app/flights/amadeus_client.py:221-228`
**Issue:** The double-checked locking pattern is correct for single-flight refresh, but `await self._refresh_token()` runs *inside* `async with self._token_lock`. If the awaiting coroutine is cancelled (asyncio task cancelled, or the surrounding ClientBuilder context manager raises during `__aexit__`), `_refresh_token` raises before populating `_access_token`/`_expires_at`, and the lock is released. The next caller will hit the slow path again — that's fine — but the state is left at the *previous* `_access_token` (possibly stale). More subtly: a `KeyError` from CR-02 would leave the lock holder raising, every concurrent waiter then re-enters the slow path under the lock and re-raises the same `KeyError`, flooding the OAuth endpoint with serialized failures rather than failing fast. Consider tracking a "last refresh failure timestamp" and short-circuiting subsequent slow-path entries within e.g. 1 second of a failure. Lower priority than CR-02 but they compound.

**Fix:** After fixing CR-02, add a quick negative-cache to break the storm:
```python
async with self._token_lock:
    now = datetime.now(UTC)
    if self._last_failure_at and (now - self._last_failure_at) < timedelta(seconds=1):
        raise APIError(...)  # the previous failure
    ...
    try:
        return await self._refresh_token()
    except APIError:
        self._last_failure_at = datetime.now(UTC)
        raise
```

### WR-05: `_parse_flight_offers` raises `KeyError` / `IndexError` on malformed Amadeus payloads, then propagates as `APIError`

**File:** `backend/app/flights/amadeus_client.py:454-495`
**Issue:** The parser indexes deeply (`offer["itineraries"][0]`, `segments[0]`, `first_seg["departure"]["at"]`, etc.) with no defensive checks. If Amadeus returns an offer with empty `itineraries` (which has been observed in some sandbox edge cases), or a missing `price.total`, the loop raises `IndexError`/`KeyError` partway through, and *all* offers parsed so far in the same response are lost. Worse, those raw exceptions escape `_search_impl` (which only catches `StatusError`/`RequestTimeoutError`/`ConnectError`), bubble out of `call_with_breaker` (which counts them as system errors and increments the breaker counter), and surface to the caller as raw `KeyError` — *not* as `APIError`. This means a single malformed offer in a 50-offer page burns a breaker slot and crashes user-facing requests, instead of being skipped with a warning.

**Fix:**
```python
for offer in offers:
    try:
        flight = self._parse_single_offer(offer, carriers_dict)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Skipping malformed Amadeus offer id=%r: %s", offer.get("id"), exc)
        continue
    flights.append(flight)
```
Refactor the per-offer body into `_parse_single_offer` and unit-test the skip-malformed path.

### WR-06: `search_flights` swallows broad `Exception` and returns it as a string to the LLM (information disclosure)

**File:** `backend/app/tools/flight_search.py:428-429`
**Issue:** `except Exception as e: return f"Unexpected error during flight search: {e}"` — this returns the raw `str(e)` of any non-`FlightSearchError` to the LLM, which then passes it through to the user. If the underlying client raises an `APIError` whose message contains internal stack info, URLs, or — worst case — credentials echoed by Amadeus (the very threat T-07-02 was added to defend against), that text now leaves the server-side trust boundary via the LLM completion. The route layer (CR-05) is careful never to echo `str(e)` over the SSE wire; this tool layer undoes that guarantee at the *content* layer.

Also: ad-hoc string returns prevent the LLM from triggering the `error_event` path at all — the user sees a normal-looking message saying "Unexpected error: ..." instead of a structured error card.

**Fix:**
```python
except FlightSearchError as e:
    return f"Flight search error: {e}"
except APIError as e:
    # APIError messages are reviewed and credential-safe (see amadeus_client._raise_from_http_status)
    return f"Flight search failed: {e.message}"
except Exception:
    logger.exception("Unexpected error in search_flights tool")
    return "Flight search failed unexpectedly. Please try again."
```

### WR-07: `failing_function` in `test_retry.py` mutates a function attribute as global state — test isolation is fragile

**File:** `backend/tests/unit/test_retry.py:18-32, 45-49`
**Issue:** `failing_function.attempts` is a module-level mutable counter on the function object, reset by an autouse fixture. This works, but: (1) parallel test execution (pytest-xdist) would race on the shared attribute; (2) if `test_retry_eventually_succeeds` happens to import `failing_function` from another module in the future, the counter bleeds across modules; (3) the assertion at line 70 (`failing_function.attempts == 3`) is the only reason this matters — a closure-scoped counter in each test would isolate the state correctly. Low priority but the pattern is a footgun.

**Fix:**
```python
async def test_retry_eventually_succeeds() -> None:
    attempts = 0

    @retry_on_failure(max_retries=3, backoff_base=0.01)
    async def func() -> str:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise APITimeoutError(message="Temporary failure")
        return "success"

    result = await func()
    assert result == "success"
    assert attempts == 3
```
Then delete `failing_function` and the autouse fixture entirely.

## Info

### IN-01: `httpx>=0.27.0` is still a runtime dependency despite ADR-008 banning it

**File:** `backend/pyproject.toml:13`
**Issue:** `pyproject.toml` line 13 keeps `httpx>=0.27.0` as a runtime dependency with the comment "For ollama API calls". ADR-008 / Phase-7 D-10 says "Outbound HTTP uses pyreqwest exclusively — never aiohttp, never httpx, never requests" (CLAUDE.md echoes this). Either the Ollama client genuinely still uses httpx (in which case the project is in an inconsistent state and ADR-008 needs an explicit carve-out) or it's been migrated and this dependency is dead. The httpx dev dep on line 42 "For testing FastAPI" is fine — TestClient genuinely depends on it. Worth a note next to the runtime dep, or a dependency cleanup.

**Fix:** If Ollama really uses httpx, document the exception in ADR-008. Otherwise, drop the runtime httpx dep.

### IN-02: `local import` of `datetime` inside `normalize_skyscanner_itinerary` is a style anti-pattern

**File:** `backend/app/tools/flight_search.py:241`
**Issue:** `from datetime import datetime # local import to avoid polluting module namespace` — but `datetime` is *already* imported at module scope on line 25 (`from datetime import UTC, date, datetime`). The local import shadows the module-level one with the same symbol; the comment is misleading. Just remove the local import.

**Fix:** Delete line 241.

### IN-03: Logger formats the default JWT secret value into the warning message

**File:** `backend/app/config.py:115-121`
**Issue:** The warning emits the literal default value `"changeme"` as part of the log line: `"JWT_SECRET is set to the default value 'changeme'"`. This isn't a real secret leak (the default is hardcoded and public), but it's a small log-noise smell — the message could just say `"JWT_SECRET is set to the default value"` and let the constant remain implicit. It also primes anyone tailing logs in a misconfigured prod env to think there's a real secret in the message.

**Fix:** Drop the `_DEFAULT_JWT_SECRET` interpolation: `"JWT_SECRET is set to the default value. Set the JWT_SECRET environment variable..."`.

### IN-04: `_iso_pt_to_minutes` silently returns 0 for unparseable durations — log when this happens

**File:** `backend/app/flights/amadeus_client.py:63-78`
**Issue:** Any duration string that doesn't match `^PT(?:(\d+)H)?(?:(\d+)M)?$` (e.g. seconds-precision `"PT2H30M15S"`, days `"P1DT2H"`) returns `0`. A 0-minute flight is not realistic; the parsed value flows into `Flight(duration_minutes=0)` and downstream filter `f.duration_minutes <= max_duration` always passes. Add a `logger.debug` (or warning) on the no-match path so unexpected formats are observable.

**Fix:**
```python
match = _PT_DURATION_RE.match(duration)
if not match:
    logger.warning("Unparseable Amadeus duration string %r; defaulting to 0 minutes", duration)
    return 0
```

### IN-05: `_to_iso_duration(0)` returns `"PT0H"` (no minutes branch when m=0), which is technically correct ISO 8601 but inconsistent with rest of formatter

**File:** `backend/app/tools/flight_search.py:67-78`
**Issue:** `f"PT{h}H{m}M" if m else f"PT{h}H"` returns `"PT0H"` when `minutes == 0`, but the docstring example uses `"PT0H"` for `0 minutes` — which renders as 0 hours, not 0 minutes. Strictly valid ISO 8601 but unusual; consider `"PT0M"` for the `minutes == 0 and hours == 0` case for parity with `_iso_pt_to_minutes` round-trip. Minor — flagged because round-trip stability would prevent silent value drift if/when that pattern gets used.

**Fix:** Optional, but for round-trip cleanliness:
```python
def _to_iso_duration(minutes: int) -> str:
    if minutes == 0:
        return "PT0M"
    h, m = divmod(minutes, 60)
    if h and m:
        return f"PT{h}H{m}M"
    if h:
        return f"PT{h}H"
    return f"PT{m}M"
```

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
