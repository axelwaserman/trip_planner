---
phase: 07-real-flight-api
reviewed: 2026-06-06T05:34:03Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - .env.example
  - .github/workflows/ci.yml
  - README.md
  - backend/app/api/main.py
  - backend/app/config.py
  - backend/app/flights/duffel_client.py
  - backend/app/llm/log_scrubbing.py
  - backend/app/tools/flight_search.py
  - backend/tests/e2e_duffel/__init__.py
  - backend/tests/e2e_duffel/conftest.py
  - backend/tests/e2e_duffel/test_duffel_client.py
  - backend/tests/fixtures/duffel/__init__.py
  - backend/tests/fixtures/duffel/offer_request_response_oneway.json
  - backend/tests/fixtures/duffel/offer_request_response_roundtrip.json
  - backend/tests/integration/test_health.py
  - backend/tests/integration/test_lifespan_flight_provider.py
  - backend/tests/unit/llm/test_log_scrubbing.py
  - backend/tests/unit/test_config_duffel.py
  - backend/tests/unit/test_duffel_client.py
  - backend/tests/unit/test_duffel_error_mapping.py
  - backend/tests/unit/test_tool_json_normalization.py
  - justfile
findings:
  critical: 0
  warning: 5
  info: 9
  total: 14
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-06T05:34:03Z
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Phase 7 introduces the Duffel `FlightAPIClient` implementation, a lifespan
auto-fallback to `MockFlightAPIClient`, and an `ApiKeyScrubber` extension for
Duffel bearer tokens. The core security posture (T-07-02) is solid:

- **Token never echoed in error messages.** `_raise_from_http_status` derives
  every `APIError.message` from the integer status alone and chains via
  `from exc` — no body content is interpolated into user-visible messages.
  Locked by `test_search_status_error_401_maps_to_api_client_error_not_retryable`.
- **SecretStr opacity preserved at the boundary.** `Settings.duffel_api_token`
  is `SecretStr | None`; the lifespan unwraps via `.get_secret_value()` exactly
  once at `DuffelFlightClient` construction. `repr()` opacity is locked.
- **Lifespan auto-fallback is uniform** for `None` and `SecretStr('')`: line
  64 of `app/api/main.py` collapses both to an empty string before the gate.
- **Composition is correct.** `@retry_on_failure` wraps `_fetch_with_retry_breaker`,
  which calls `call_with_breaker` → `_search_impl`. The open-breaker remap to
  `APIServerError(retryable=False)` short-circuits tenacity (regression-locked).
- **ADR-008 holds.** No `requests`/`aiohttp`/`httpx` import was introduced by
  this phase — only `pyreqwest`. (Pre-existing httpx imports in
  `app/llm/providers/{ollama,lmstudio}.py` are out of scope.)
- **Test isolation is clean.** Unit tests patch `_search_impl` or mock
  `ClientBuilder` — no real network in unit/integration suites. The
  `e2e_duffel` suite is gated at collection time on `DUFFEL_API_TOKEN`.

The findings below are quality-tier — defensive hardening and documentation
drift. None block ship of Phase 7.

## Warnings

### WR-01: Bearer token stored as raw `str` on the client instance

**File:** `backend/app/flights/duffel_client.py:182`
**Issue:** `self._api_token = api_token` stores the bearer as a plain string.
`SecretStr` opacity at the `Settings` boundary is unwrapped once and the raw
string then lives indefinitely on the instance. Any code path that ends up
`repr()`-ing the client (e.g. an unhandled exception traceback that captures
`self`, a debug `print(self.__dict__)`, a future logging statement that takes
`%r` of the client) will surface the live token. The `ApiKeyScrubber` regex
is the only line of defense at that point, and it requires the token to
match the `duffel_(test|live)_[A-Za-z0-9_-]{20,}` shape — synthetic test
tokens (e.g. the unit-test literal `"dummy"`) will not be redacted.
**Fix:** Wrap on the instance and unwrap only at the call site:
```python
def __init__(self, api_token: str, base_url: str) -> None:
    self._api_token: SecretStr = SecretStr(api_token)
    ...

# at call sites:
.bearer_auth(self._api_token.get_secret_value())
```
A custom `__repr__` that omits `_api_token` is a weaker but acceptable
alternative.

### WR-02: `_search_impl` does not translate parser/shape errors into `APIError`

**File:** `backend/app/flights/duffel_client.py:368`
**Issue:** Lines 358–371 await `resp.json()` and then dereference
`payload["data"]["offers"]` and `_normalize_offer(o)`. If Duffel returns a
2xx with an unexpected JSON shape (missing `data`, missing `offers`, missing
`slices`/`segments`/`marketing_carrier`/`total_amount`), a raw `KeyError` /
`ValueError` / `TypeError` propagates. That bypasses the `APIError`
contract callers depend on:

- `retry_on_failure._is_retryable` returns `False` for non-`APIError`, so
  the exception is NOT retried — but the failure is also NOT counted by
  `pybreaker.is_system_error`, which gates on `Exception` subclasses by
  default (raw `KeyError` is an `Exception`, so it WILL count, but the
  caller sees `KeyError`, not `APIServerError`).
- The user-facing `search_flights` tool catches the bare `Exception` and
  returns `f"Unexpected error during flight search: {e}"` — the raw
  `KeyError('data')` becomes user-facing prose.

**Fix:** Wrap the body-parsing block in a try/except and translate to
`APIServerError(retryable=False)` (Duffel returned 2xx with a shape we
cannot parse — retry will not fix it):
```python
try:
    offers: list[dict[str, Any]] = payload["data"]["offers"]
    return [self._normalize_offer(o) for o in offers[:limit]]
except (KeyError, ValueError, TypeError) as exc:
    raise APIServerError(
        message="Duffel response shape unexpected",
        retryable=False,
    ) from exc
```

### WR-03: `details.get("status", 0)` silently falls through to retryable `APIServerError`

**File:** `backend/app/flights/duffel_client.py:241, 361`
**Issue:** When pyreqwest's `StatusError` carries a `details` dict without a
`"status"` key, `int(details.get("status", 0))` evaluates to `0`. That
trips the unknown-status branch in `_raise_from_http_status` (line 152) and
surfaces as `APIServerError(retryable=True)`. A non-HTTP `StatusError`
would therefore burn the entire 4-attempt retry budget instead of failing
fast. Additionally, if `details["status"]` is ever a string (`"401"`),
`int(...)` succeeds — but if it is ever `None` or a non-int/non-str shape
(e.g. a future API change), `int(...)` raises `TypeError` outside the
`except` block, escaping the translation contract entirely.
**Fix:** Defend the parse and treat missing/unparseable status as a
non-retryable mapping error:
```python
except StatusError as exc:
    details = getattr(exc, "details", None) or {}
    raw_status = details.get("status")
    try:
        status = int(raw_status) if raw_status is not None else 0
    except (TypeError, ValueError):
        status = 0
    _raise_from_http_status(status, exc)
```

### WR-04: `search()` docstring contradicts the `del offset` line below it

**File:** `backend/app/flights/duffel_client.py:403, 424`
**Issue:** The docstring on line 403 says "`offset` is honored but capped",
which a reader interprets as "offset is applied to slice the result list".
Three lines later the implementation reads `del offset  # explicitly unused`.
Either statement alone is fine; together they mislead anyone debugging a
caller that relies on `offset > 0`. The Amadeus-phase CR-01 regression-lock
is the implicit reason offset is dropped, but the docstring should say so.
**Fix:** Replace the contradictory "honored but capped" wording with
"ignored — Duffel's single-round-trip flow does not paginate; documented
for ABC compatibility (CR-01 regression-lock)." Match the wording on
line 418–419 of the same docstring (`Args: offset:`), which is already
correct.

### WR-05: `e2e` CI job runs every push without an LLM gate or skip mechanism

**File:** `.github/workflows/ci.yml:89-119`
**Issue:** The `e2e` job runs `uv run pytest tests/e2e/` unconditionally on
push to master and on pull requests. Per `CLAUDE.md` and
`backend/tests/e2e/README.md`, the e2e suite is "currently a symbolic CI
gate" expecting a real LLM. Without Ollama / a mock LLM gate, this job will
either fail-on-collect, hang waiting for `localhost:11434`, or pass only
because the suite is empty. There is no `if:` clause analogous to
`duffel-e2e`'s `vars.DUFFEL_E2E_ENABLED == 'true'`. This is pre-existing
relative to Phase 7 but the same workflow file was edited for the
`duffel-e2e` job, so the missing parity is in scope for review.
**Fix:** Either gate the `e2e` job behind `vars.E2E_ENABLED == 'true'`
(symmetric with `duffel-e2e`) or document in the workflow file why the
job runs unconditionally and what it actually exercises. If the suite is
intentionally empty in CI, mark it `if: false` with a TODO comment.

## Info

### IN-01: `logger` declared but never used in `duffel_client.py`

**File:** `backend/app/flights/duffel_client.py:47`
**Issue:** `logger = logging.getLogger(__name__)` is created at module scope
but never referenced. Either dead code or a placeholder for not-yet-added
diagnostic logging.
**Fix:** Delete the binding (and the `import logging` on line 23) until a
log statement is added, OR add the planned WARN/INFO calls that justify
keeping it.

### IN-02: README "Tech Stack" lists React 18 but `CLAUDE.md` and code use React 19

**File:** `README.md:154`
**Issue:** Line 154 advertises `**React 18** - UI framework`. `CLAUDE.md` (and
the `frontend/` package) reference React 19. Documentation drift.
**Fix:** Update to `**React 19** - UI framework`.

### IN-03: README has a duplicate `Quick Start` section that contradicts the canonical Quickstart

**File:** `README.md:160-189`
**Issue:** Lines 160–207 are a stale `## Quick Start` (with capitalized
"S") that duplicates the canonical `## Quickstart` block at the top of the
file (lines 6–67) and includes wrong commands (`uv run mypy src/` — the
project uses `app/`, not `src/`). The duplicate section also instructs
users to `cp .env.example .env` from `backend/`, conflicting with the
top-level `cp .env.example .env` instruction.
**Fix:** Delete lines 160–207 (or merge any non-redundant content into the
canonical Quickstart). Mypy command should read `uv run mypy app/` if
preserved.

### IN-04: `_iso_pt_to_minutes("PT")` silently returns 0

**File:** `backend/app/flights/duffel_client.py:58-76`
**Issue:** The regex `^PT(?:(\d+)H)?(?:(\d+)M)?$` matches the bare string
`"PT"` (both groups optional), yielding `hours=0` and `minutes=0`. A
zero-duration `Flight` is then constructed. The `Flight` model may reject
`duration_minutes=0`, but if not, the user sees a flight with "PT0H" total
duration.
**Fix:** Tighten the regex to require at least one of `H` or `M`:
```python
_PT_DURATION_RE = re.compile(r"^PT(?=\d)(?:(\d+)H)?(?:(\d+)M)?$")
```
or raise explicitly when both groups are `None`.

### IN-05: `cabin_raw.lower()` cast trusts the Flight validator

**File:** `backend/app/flights/duffel_client.py:332`
**Issue:** `cast("BookingClass", cabin_raw.lower())` blind-casts whatever
Duffel returns for `cabin_class` ("economy" / "premium_economy" / "business" /
"first") onto the project's `BookingClass` Literal. The comment says the
`Flight` validator narrows it, but `cast` defeats type-checker visibility
into the failure mode. If Duffel adds a new cabin string, the cast
silently passes mypy and the runtime exception only fires inside the
validator.
**Fix:** No code change required if the validator is robust; consider
narrowing explicitly via an `if cabin_raw not in get_args(BookingClass)`
check that raises `APIServerError(retryable=False)` so the failure surfaces
through the existing error contract instead of as a Pydantic
`ValidationError`.

### IN-06: Round-trip queries surface only the outbound slice

**File:** `backend/app/flights/duffel_client.py:287-333`
**Issue:** `_normalize_offer` reads `offer["slices"][0]` only and constructs
a single `Flight`. For round-trip queries (D-07 emits two slices), the
return-leg data is dropped on the floor — the caller cannot see return
times, prices, or stops. Documented in the docstring + locked by
`test_normalize_offer_roundtrip_uses_outbound_slice`, but the user-facing
result is incomplete data when `query.return_date is not None`.
**Fix:** Either (a) document this loudly in the user-facing Phase 7
SUMMARY as a known v1 limitation, or (b) extend `Flight` to carry an
optional `return_segments` field. For v1 this is acceptable but the
contract should be explicit in the `search_flights` tool docstring (which
currently says nothing about return legs being dropped).

### IN-07: `(test|live)` capture group in scrubber regex is unused

**File:** `backend/app/llm/log_scrubbing.py:48`
**Issue:** The pattern `duffel_(test|live)_[A-Za-z0-9_-]{20,}` uses a
capturing group for `test|live` but the replacement template
`"duffel_[REDACTED]"` does not reference it. Minor inefficiency and
slightly misleading regex.
**Fix:** Use a non-capturing group:
```python
(re.compile(r"duffel_(?:test|live)_[A-Za-z0-9_-]{20,}"), "duffel_[REDACTED]"),
```

### IN-08: `ChatService.cleanup_expired_conversations(max_age_seconds=0)` runs on shutdown

**File:** `backend/app/api/main.py:123`
**Issue:** Out of strict Phase 7 scope, but the lifespan was edited in
this phase. `max_age_seconds=0` deletes all conversations on every
shutdown — including a plain `uvicorn` reload. If this is intentional
(test/dev), document it; if not, it is data loss on hot-reload.
**Fix:** Confirm intent. If preserved deliberately, add a comment
explaining "drop all on shutdown is a dev convenience". If unintentional,
gate behind a `Settings.cleanup_on_shutdown` flag.

### IN-09: `_apply_filters(max_stops)` reapplies a filter Duffel already enforced server-side

**File:** `backend/app/flights/duffel_client.py:79-97, 425-426`
**Issue:** D-14 sends `max_connections` to Duffel server-side; D-06 then
reapplies the same filter client-side. The docstring on line 415
acknowledges "also reapplied client-side for safety". This is defensive
duplication, not a bug — flagged only because it's wasted work in the
common path. If Duffel ever ships an offer with `segments > max_stops + 1`,
the client filter catches it; otherwise it's a no-op.
**Fix:** No action required. Consider removing the client-side reapply
once the integration is stable, or add a metric to track how often it
actually filters anything.

---

_Reviewed: 2026-06-06T05:34:03Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
