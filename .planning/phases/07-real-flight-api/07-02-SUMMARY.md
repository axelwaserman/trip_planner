---
phase: 07-real-flight-api
plan: 02
subsystem: vendor-flight-client
tags: [duffel, http-client, pyreqwest, retry, circuit-breaker, normalization, phase-7]
requirements: [REQ-real-flight-api]
dependency_graph:
  requires:
    - "backend/app/tools/flight_client.py::FlightAPIClient (existing ABC)"
    - "backend/app/tools/retry.py::retry_on_failure (existing)"
    - "backend/app/tools/circuit_breaker.py::call_with_breaker (existing)"
    - "backend/app/exceptions.py::APIError hierarchy (existing)"
    - "backend/app/flights/models.py::Flight, FlightQuery (existing; return_date already present)"
  provides:
    - "DuffelFlightClient (FlightAPIClient impl)"
    - "_DUFFEL_VERSION='v2' module constant (D-03)"
    - "_raise_from_http_status mapping helper (D-04)"
    - "Recorded Duffel offer JSON fixtures (one-way + round-trip)"
  affects:
    - "Plan 07-03 lifespan branch (constructs DuffelFlightClient when token present)"
    - "Plan 07-04 e2e_duffel suite (consumes the client + auth probe)"
    - "Plan 07-05 README credential-setup section"
tech_stack:
  added: []
  patterns:
    - "Async retry-outside-breaker-inside composition (D-12-class)"
    - "HTTP-status-driven error mapping (D-04 — body content never echoed)"
    - "Naive-ISO + UTC-attach normalization (D-09 / Pitfall 2)"
    - "Recorded JSON fixtures for offline _normalize_offer coverage"
key_files:
  created:
    - "backend/app/flights/duffel_client.py"
    - "backend/tests/unit/test_duffel_client.py"
    - "backend/tests/unit/test_duffel_error_mapping.py"
    - "backend/tests/fixtures/duffel/__init__.py"
    - "backend/tests/fixtures/duffel/offer_request_response_oneway.json"
    - "backend/tests/fixtures/duffel/offer_request_response_roundtrip.json"
  modified: []
decisions:
  - "pyreqwest's RequestBuilder uses body_json(body) (not .json(body) as the PATTERNS template assumed); confirmed via runtime introspection of pyreqwest 0.12.0."
  - "StatusError carries details as a TypedDict StatusErrorDetails with keys {causes, status} only; no body field. T-07-02 message-no-body invariant therefore tested by stuffing sensitive content into the StatusError MESSAGE itself, not into details — same threat model, real surface."
  - "search() takes offset as a parameter (ABC contract) but explicitly del offset's it inside the method body to satisfy mypy strict + the D-06 'offset is documented-ignored' rule. Documented in the docstring."
metrics:
  duration_minutes: 13
  tasks_completed: 3
  tests_added: 19
  completed_date: "2026-06-06"
---

# Phase 7 Plan 2: DuffelFlightClient + Recorded Fixtures Summary

`DuffelFlightClient` lands as the production `FlightAPIClient` impl: a 403-line module that issues a single `POST /air/offer_requests?return_offers=true` per search via `pyreqwest`, composes `@retry_on_failure` outer / `call_with_breaker` inner / `_search_impl` innermost (D-12-class), and routes HTTP errors through a status-only mapping helper that never echoes response body content. Two recorded JSON fixtures plus 19 unit tests (11 client + 8 parametrised mapping rows) lock the contract for downstream lifespan + e2e_duffel plans.

## What Shipped

### Final LOC count

`backend/app/flights/duffel_client.py` — **403 lines** (target was 200–350).

The 53-line overshoot is concentrated in module/method docstrings — every public method has a full Args/Returns/Raises block per CLAUDE.md "Public APIs get docstrings" rule, plus the module docstring documents D-03/D-04/D-09/T-07-02 wiring inline so future readers don't grep the threat register. Stripping docstrings would land the file ~280 lines, well within target. Treating the docstring depth as in-scope; flagging the overshoot for transparency rather than reflowing.

### Test count delta

| File | Tests |
|------|-------|
| `backend/tests/unit/test_duffel_client.py` (NEW) | 11 |
| `backend/tests/unit/test_duffel_error_mapping.py` (NEW) | 8 (parametrised) |

19 new tests; all pass. Full unit suite (`backend/tests/unit/`) green at **295 passed, 1 pre-existing skipped** — zero regressions.

### Forbidden-imports grep

```bash
$ grep -cE '^(import|from) (aiohttp|httpx|requests|urllib3)' backend/app/flights/duffel_client.py
0
```

ADR-008 enforced — outbound HTTP via `pyreqwest` exclusively.

### Composition pin (D-12-class)

| Layer | Implementation | Line |
|-------|----------------|------|
| Outer | `@retry_on_failure(max_retries=3, backoff_base=2.0)` | 324 |
| Middle | `call_with_breaker(self._breaker, self._search_impl, ...)` | inside `_fetch_with_retry_breaker` |
| Inner | `_search_impl` (pyreqwest POST) | uses `ClientBuilder().timeout(...).error_for_status(True).build()` |
| Open-breaker remap | `pybreaker.CircuitBreakerError` → `APIServerError(retryable=False)` | inside `_fetch_with_retry_breaker` |

Verified by `test_circuit_breaker_open_raises_apiservererror_not_retried`: with `fail_max=1`, the first `search()` call trips the breaker (one `_search_impl` await), tenacity short-circuits because the remapped error has `retryable=False`, the second call hits the already-open breaker without ever awaiting `_search_impl`. Final `await_count == 1`.

### D-04 status mapping (parametrised proof)

| Status | Type | Retryable |
|--------|------|-----------|
| 401 | `APIClientError` | False |
| 400 | `APIClientError` | False |
| 404 | `APIClientError` | False |
| 422 | `APIClientError` | False |
| 429 | `APIRateLimitError` | True |
| 500 | `APIServerError` | True |
| 503 | `APIServerError` | True |
| 599 | `APIServerError` | True (unknown-5xx fall-through) |

Each row asserts `retryable` flag + `__cause__` chained correctly. Messages contain the status integer ONLY — `test_search_status_error_401_maps_to_api_client_error_not_retryable` asserts that sensitive content in a real `StatusError` ("Unauthorized: user_email=victim@example.com leaked") does NOT survive into `APIError.message`. T-07-02 / Pitfall 3 locked.

### Body construction (D-07 / D-13 / D-14)

| Test | Assertion |
|------|-----------|
| `test_build_offer_request_body_oneway` | `len(slices)==1`, no `max_connections`, single adult, `cabin_class=="economy"` |
| `test_build_offer_request_body_roundtrip_two_slices` | `len(slices)==2`, return slice has flipped origin/destination + `return_date` |
| `test_build_offer_request_body_max_stops_maps_to_max_connections` | every slice has `max_connections==1` when `max_stops=1`; key absent when `max_stops=None` |
| `test_build_offer_request_body_passengers_list_length` | `passengers=3` → `[{type:adult}]*3` |

### D-06 offset cap regression-lock (CR-01 prevention)

`test_search_offset_capped_returns_head_at_limit`: patches `_search_impl` to return 5 mock flights, calls `search(query, limit=2, offset=2)`, asserts `len(result)==2` AND result equals the first two of the mocked list (head, not skip). The argument `offset=2` is explicitly passed AND ignored — that's the regression-lock.

### D-09 normalization (naive → UTC) + D-10 cabin path

| Test | Assertion |
|------|-----------|
| `test_normalize_offer_oneway_produces_tz_aware_flight` | `tzinfo is not None` for both endpoints; `stops==1` from 2 segments; `booking_class=="economy"` from per-segment passenger cabin path |
| `test_normalize_offer_naive_datetime_attaches_utc` | `tzinfo == UTC` specifically (D-09 lock) |
| `test_normalize_offer_roundtrip_uses_outbound_slice` | round-trip fixture → `_normalize_offer` reads slices[0] only; flight_number contains "1234" (outbound), not "5678" (return) |

## Tasks

### Task 1: Recorded Duffel JSON fixtures (one-way + round-trip)

Commit **`26dd12c`** — `test(07-02): add Duffel offer JSON fixtures (one-way + round-trip)`.

Hand-crafted rather than captured (no local Duffel sandbox token). Each fixture follows the SDK-documented field shape from 07-RESEARCH §"Code Examples 3":
- One-way: 1 slice, 2 segments (MAD → PMI → BCN connecting itinerary; proves `stops==1` normalization).
- Round-trip: 2 slices (outbound MAD → BCN with flight number 1234, return BCN → MAD with flight number 5678 — distinct so test assertions can prove the impl reads `slices[0]` and not `slices[1]`).
- All segment `departing_at` / `arriving_at` are NAIVE ISO 8601 (no `Z`, no offset) — D-09 / Pitfall 2 lock.
- `total_amount` is JSON string per Duffel convention.
- File sizes: 4 KB each (target ≤10 KB).
- `grep -E 'duffel_(test|live)_[A-Za-z0-9_-]{20}'` returns no matches — no token leakage.

### Task 2: `DuffelFlightClient` implementation

Commit **`9743ad5`** — `feat(07-02): add DuffelFlightClient with retry+breaker+pyreqwest composition`.

403-line module per the simplified-Amadeus template in 07-PATTERNS.md §"backend/app/flights/duffel_client.py". The OAuth2 token-cache layer (`_get_token`, `_refresh_token`, `asyncio.Lock`, double-checked locking, malformed-body guard, `_REFRESH_BUFFER_SECONDS`, `_TOKEN_PATH`) is fully omitted because Duffel uses static bearer tokens.

mypy strict clean, ruff lint + format clean, all required greps return single matches:
- `_DUFFEL_VERSION = "v2"` — line 52 (D-03 wire-version contract constant)
- `def _raise_from_http_status` — line 111
- `class DuffelFlightClient(FlightAPIClient):` — line 155
- `pybreaker.CircuitBreaker(... fail_max=5 ...)` — lines 184–185
- `@retry_on_failure(max_retries=3, backoff_base=2.0)` — line 324
- `flights[:limit]` (D-06 cap inside `search`) — line 379

Instantiation + `health_check()` smoke test passes: `asyncio.run(c.health_check()) is True` — no network call.

### Task 3: Unit tests (composition, error mapping, normalization, offset cap)

Commit **`b027bbc`** — `test(07-02): unit-test DuffelFlightClient (composition, normalization, mapping)`.

19 tests across two files; mypy strict clean, ruff lint + format clean. Sleep patching uses `patch("tenacity.nap.time.sleep", return_value=None)` so retry tests run in milliseconds rather than seconds.

## Deviations from Plan

### `[Rule 1 - Bug] pyreqwest body method name correction`

- **Found during:** Task 2 implementation
- **Issue:** PATTERNS template specified `.json(body)` but pyreqwest 0.12.0's `RequestBuilder` actually exposes `body_json(body)` — `.json` does not exist. A literal copy of the template would have raised `AttributeError` at first request.
- **Fix:** Used `body_json(body)` after runtime introspection of the installed pyreqwest version. Verified via `dir(rb)` showing `body_json` and absence of `json`.
- **Files modified:** `backend/app/flights/duffel_client.py`
- **Commit:** `9743ad5`

### `[Rule 1 - Bug] StatusError details TypedDict shape`

- **Found during:** Task 3 mypy run
- **Issue:** Initial test attempt used `MagicMock(spec=StatusError)` with a custom `details` dict containing a `body` key. Two failures: (a) `raise X from MagicMock` is invalid because `MagicMock` is not a real `BaseException` subclass — Python raises `TypeError: exception causes must derive from BaseException`; (b) `StatusErrorDetails` is a TypedDict with keys `{causes, status}` only — extra `body` key fails mypy `typeddict-unknown-key`.
- **Fix:** Construct a real `StatusError("Unauthorized: user_email=victim@example.com leaked", details={"status": 401, "causes": None})`. Sensitive content moved into the message field — same threat surface (an accidentally-leaky impl could echo `str(exc)` which surfaces the message), real exception subclass for `from exc` chaining.
- **Files modified:** `backend/tests/unit/test_duffel_client.py`
- **Commit:** `b027bbc`

### `[Rule 1 - Bug] mypy strict — return-Any from json.loads`

- **Found during:** Task 3 mypy run
- **Issue:** `return json.loads((_FIXTURES_DIR / name).read_text())` flagged `[no-any-return]` because `json.loads` returns `Any`.
- **Fix:** Annotated the intermediate variable: `parsed: dict[str, Any] = json.loads(...); return parsed`.
- **Files modified:** `backend/tests/unit/test_duffel_client.py`
- **Commit:** `b027bbc`

### `[Note] LOC overshoot vs target`

- The plan target was 200–350 lines for `duffel_client.py`; the file is 403 lines. Cause: extensive Args/Returns/Raises docstrings on every public + protected method, plus module-level docstrings documenting D-03/D-04/D-09/T-07-02 wiring inline. Stripping docstrings would land the file at ~280 lines.
- Not a bug; treating the docstring depth as a feature per CLAUDE.md "Public APIs get docstrings". Flagged for transparency.

### `[Note] body_json vs json template adjustment`

- 07-PATTERNS.md §S2 shows the pyreqwest builder chain ending in `.json(body)`. The actual pyreqwest 0.12.0 method is `body_json(body)`. Suggest the PATTERNS doc be updated in a future plan to reflect the real method name so this discovery does not need to be repeated.

## Auth gates

None — no authentication required to execute this plan (no Duffel API calls; offline tests + recorded fixtures only).

## Threat Flags

None — this plan implements the mitigations declared in the plan's `<threat_model>` (T-07-02-01 through T-07-02-08) and does not introduce new security-relevant surface beyond what was authored:

- **T-07-02-01** (bearer leakage in pyreqwest debug logs) — defended by Plan 07-01 `ApiKeyScrubber`; verified upstream.
- **T-07-02-02** (`errors[0]` body-content echo) — defended by `_raise_from_http_status` constructing messages from `status` only; locked by `test_search_status_error_401_maps_to_api_client_error_not_retryable`.
- **T-07-02-03** (SSRF via `base_url`) — accepted; lifespan injection of fixed string is Plan 07-03's responsibility.
- **T-07-02-04** (retry storm) — defended by tenacity bound + pybreaker open-circuit short-circuit; locked by `test_circuit_breaker_open_raises_apiservererror_not_retried`.
- **T-07-02-05** (401 retry storm) — defended by D-04 401 → `retryable=False`; locked by parametrised mapping table.
- **T-07-02-06** (round-trip date injection) — defended by existing `FlightQuery.validate_dates`; no new surface.
- **T-07-02-07** (Pitfall 6 ValidationError at boot) — Plan 07-01 dependency; reaffirmed.
- **T-07-02-08** (forbidden HTTP libs) — locked by acceptance grep returning 0.

## Notes for Plan 07-03 (lifespan)

- Constructor signature is `DuffelFlightClient(api_token: str, base_url: str)`. Lifespan should pass `settings.duffel_api_token.get_secret_value()` for the token and the literal `"https://api.duffel.com"` for the base URL.
- The empty-string-token edge case (`SecretStr('')` from the `.env.example` placeholder) was flagged by Plan 07-01 — Plan 07-03's auto-fallback predicate should be `settings.duffel_api_token is None or not settings.duffel_api_token.get_secret_value()` so the empty-string case maps to "no token".

## Self-Check: PASSED

**Files verified to exist:**
- `backend/app/flights/duffel_client.py` — FOUND
- `backend/tests/unit/test_duffel_client.py` — FOUND
- `backend/tests/unit/test_duffel_error_mapping.py` — FOUND
- `backend/tests/fixtures/duffel/__init__.py` — FOUND
- `backend/tests/fixtures/duffel/offer_request_response_oneway.json` — FOUND
- `backend/tests/fixtures/duffel/offer_request_response_roundtrip.json` — FOUND

**Commits verified to exist (on `worktree-agent-a51426b4c3c06b409`):**
- `26dd12c` test(07-02): add Duffel offer JSON fixtures (one-way + round-trip)
- `9743ad5` feat(07-02): add DuffelFlightClient with retry+breaker+pyreqwest composition
- `b027bbc` test(07-02): unit-test DuffelFlightClient (composition, normalization, mapping)
