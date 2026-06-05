# Phase 7: Real Flight API - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace `MockFlightAPIClient` with a real **Amadeus** client behind the existing `FlightAPIClient` ABC. Outbound HTTP uses **`pyreqwest`** per ADR-008. Vendor-neutral JSON contract from Phase 4.6 is the canonical normalization target. Mock client remains the test default via DI override. Real-API tests are gated on `AMADEUS_*` secrets.

In scope:
- `AmadeusFlightClient` implementation of `FlightAPIClient` (search, health_check, get_flight_details, check_availability)
- Amadeus OAuth2 client_credentials token lifecycle (in-process cache + concurrent-refresh lock)
- Mapping Amadeus `FlightOffer` → vendor-neutral JSON (full Phase 4.6 contract incl. multi-segment + layovers)
- Settings flag `amadeus_env` (`test` | `prod` | `mock`) + auto-fallback to mock when creds missing
- Healthcheck endpoint reports `flight_provider: 'real' | 'mock'`
- Replace `backend/app/tools/retry.py` project-wide with **tenacity**-based decorator (preserve existing call sites' API)
- Add **pybreaker** circuit breaker around Amadeus calls
- Real-API integration tests in `backend/tests/e2e_amadeus/` with dedicated CI job gated on `AMADEUS_*` secrets
- Documentation: credential setup for local + CI

Out of scope (deferred):
- Rate limiting (per ADR-009; Phase 8 if anywhere)
- Cross-vendor (Skyscanner, Google) — v1 ships Amadeus only; contract designed in Phase 4.6 already covers them
- In-process result caching with TTL — passthrough only for v1
- Aggressive retry tuning (jitter, Retry-After header) — defaults now; Phase 8 hardens if needed

</domain>

<decisions>
## Implementation Decisions

### Auth + token lifecycle
- **D-01:** Token cache strategy: **in-process with proactive refresh, inline-on-call + concurrent-refresh lock**. Cache token + `expires_at` on the `AmadeusFlightClient` instance. On each call, if `now >= expires_at - 60s`, acquire `asyncio.Lock` and refresh; concurrent callers wait on the same lock so only one refresh fires.
- **D-02:** No persistence across restarts. First call after boot fetches a fresh token. OAuth2 client_credentials grant against `https://test.api.amadeus.com/v1/security/oauth2/token` (or prod equivalent).
- **D-03:** Token refresh failures bubble as a wrapped `APIError(retryable=True)` so the tenacity retry layer can re-attempt.

### Endpoint env + mock fallback
- **D-04:** New `Settings.amadeus_env: Literal["test", "prod", "mock"] = "test"`. Base URL selected from env: `test` → `https://test.api.amadeus.com`, `prod` → `https://api.amadeus.com`, `mock` → no client constructed.
- **D-05:** Auto-fallback at lifespan: if `amadeus_env != "mock"` and either `AMADEUS_API_KEY` or `AMADEUS_API_SECRET` is missing, log a `WARN` line (`"AMADEUS_* creds missing — falling back to MockFlightAPIClient"`) and instantiate `MockFlightAPIClient` instead. No startup failure — local devs without keys still get a working stack.
- **D-06:** Healthcheck endpoint (`/healthz` or equivalent) reports `flight_provider: "real" | "mock"` so the choice is observable from outside the process.

### Field mapping coverage
- **D-07:** Full Phase 4.6 vendor-neutral contract including multi-segment journeys (`segments[]`) and layovers. Required fields mapped 1:1: price `{amount, currency}`, IATA endpoint codes, ISO-8601 times with timezone, carriers `{iata, name}`, `count`, echoed `query`.
- **D-08:** Best-effort fields: terminal info (when present in Amadeus response), fare class, baggage allowance. Missing values omitted, not stubbed.
- **D-09:** No raw-payload escape hatch. Vendor-neutral shape is the only output. Diagnostics flow through structured logs (Phase 8).

### Retry + circuit breaker
- **D-10:** **Replace `backend/app/tools/retry.py` project-wide with tenacity-based implementation.** Reimplement `retry_on_failure` as a thin tenacity wrapper preserving the existing public API (`max_retries`, `backoff_base`, `exceptions` params) so call sites in current code don't change. Delete hand-rolled internals. Adds `tenacity` to `pyproject.toml`; removes any duplicated retry logic.
- **D-11:** Defaults preserved: `max_retries=3`, exponential backoff (`backoff_base=2.0`), retry on `APIError(retryable=True)`. No jitter, no `Retry-After` header parsing — Phase 8 owns aggressive tuning. Map Amadeus 429 + 5xx → `retryable=True`; 4xx (non-429) → `retryable=False`.
- **D-12:** **Circuit breaker via `pybreaker`** wrapped around `AmadeusFlightClient.search` (and other live-call methods). Compose with tenacity: tenacity wraps the inner HTTP call, pybreaker wraps the full retry block. Add `pybreaker` to `pyproject.toml`. Default thresholds: open after 5 consecutive failures, 60s reset timeout (tunable via Settings if simple; otherwise hardcode and revisit in Phase 8).
- **D-13:** Open-breaker behavior: raise `APIError` mapped from `pybreaker.CircuitBreakerError`. Caller (`search_flights` tool) propagates; the chat layer surfaces the user-visible error per the existing `StreamEvent` error path (Phase 4.7).

### Test gating
- **D-14:** Real-API tests live in **`backend/tests/e2e_amadeus/`** (new directory). Default `pytest`, `just test`, `just test-unit`, `just test-integration`, `just test-e2e` do NOT run them. A dedicated CI workflow / job runs them, gated on `AMADEUS_*` repository secrets. PR CI never requires keys.
- **D-15:** Tests assert: token fetch + cache, real search returns ≥1 result for a known route, error mapping (force a 429 if possible, or document the limitation), full vendor-neutral shape after mapping.

### Claude's Discretion
- Exact tenacity API surface (`@retry` decorator vs `Retrying` class) — pick whichever maps more cleanly onto the current `retry_on_failure` signature; preserve callers.
- Module layout: `backend/app/flights/amadeus_client.py` (or similar) — pattern-match Phase 6's split (`MessageStore`/`PostgresMessageStore`) for the `FlightAPIClient` ↔ `AmadeusFlightClient` split.
- Whether circuit-breaker thresholds are Settings-driven or hardcoded — defer to planner; lean toward hardcoded for v1, Settings if trivial.
- Healthcheck endpoint placement — extend existing `/healthz` if present, otherwise add minimal endpoint in `app/api/`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project specs + ADRs
- `.planning/REQUIREMENTS.md` §REQ-real-flight-api — phase requirement (Amadeus, pyreqwest, retry+breaker reuse, mock as test default, secrets gating)
- `.planning/ROADMAP.md` §"Phase 7: Real Flight API" — goal and 4 success criteria
- `ARCHITECTURE.md` ADR-008 — pyreqwest mandate for outbound HTTP (forbids aiohttp/httpx)
- `ARCHITECTURE.md` ADR-009 — no rate limiting in v1
- `.planning/phases/04.6-vendor-neutral-tool-json/04.6-CONTEXT.md` — vendor-neutral JSON contract Amadeus must normalize into
- `.planning/phases/04.7-error-handling-streamevent-hierarchy/04.7-CONTEXT.md` — StreamEvent error path the breaker/retry surface emits into

### Existing code (must read before implementing)
- `backend/app/tools/flight_client.py` — `FlightAPIClient` ABC (current `search`, `health_check`, `get_flight_details`, `check_availability` signatures)
- `backend/app/tools/flight_search.py` — `search_flights` tool that consumes `FlightAPIClient`; DI rewire path from Phase 5/6
- `backend/app/tools/retry.py` — current retry decorator (TO BE REPLACED with tenacity wrapper preserving the public API)
- `backend/app/exceptions.py` — `APIError` hierarchy (`APITimeoutError`, `APIRateLimitError`, `APIServerError`, `APIClientError`, `FlightSearchError`); `retryable` flag semantics
- `backend/app/flights/models.py` — `Flight`, `FlightSegment`, `FlightQuery`, `FlightSearchResult`, `BookingClass`, `SortBy` (the vendor-neutral target shapes)
- `backend/app/config.py` — `Settings` (where `amadeus_env`, `amadeus_api_key`, `amadeus_api_secret` go)
- `backend/app/api/main.py` — `lifespan` (where the auto-fallback decision happens; where the real client is constructed and stashed on `app.state`)

### Vendor docs
- Amadeus OAuth2 token endpoint — https://developers.amadeus.com/self-service/apis-docs/guides/authorization
- Amadeus Flight Offers Search v2 — https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search
- pybreaker — https://github.com/danielfm/pybreaker
- tenacity — https://tenacity.readthedocs.io/

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FlightAPIClient` ABC (`backend/app/tools/flight_client.py:13`) — abstract surface; `AmadeusFlightClient` implements it.
- `MockFlightAPIClient` — keep as-is, becomes the auto-fallback target and the default in unit/integration tests.
- `APIError` hierarchy with `retryable` flag — drives tenacity retry decisions; map Amadeus HTTP status codes onto these.
- `Flight`, `FlightSegment`, `FlightQuery`, `FlightSearchResult` (`backend/app/flights/models.py`) — already vendor-neutral; mapping target.
- DI seam from Phase 5/6 — `FlightAPIClient` provided via `Depends(get_flight_client)` on `app.state`. `AmadeusFlightClient` slots in without route-layer changes.

### Established Patterns
- ABC + concrete impls (Phase 6's `MessageStore`/`PostgresMessageStore` split mirrors what `FlightAPIClient`/`AmadeusFlightClient` should look like).
- `pyreqwest` for all outbound HTTP — no aiohttp, no httpx, no requests.
- Async I/O end-to-end; no sync calls in async paths.
- Settings-driven env selection (lifespan branches on `Settings.*`).
- Lifespan singleton construction; clients stashed on `app.state`.

### Integration Points
- Lifespan (`backend/app/api/main.py::lifespan`) — branch on `amadeus_env` + cred presence; construct either `AmadeusFlightClient(...)` or `MockFlightAPIClient()`; stash on `app.state.flight_client`.
- `search_flights` tool — already consumes `FlightAPIClient` via DI; no signature change.
- `Settings` — add `amadeus_env`, `amadeus_api_key`, `amadeus_api_secret`, optional `amadeus_breaker_*` knobs.
- Healthcheck endpoint — surface `flight_provider` field.
- CI — new workflow file (or job) gated on `secrets.AMADEUS_API_KEY` / `secrets.AMADEUS_API_SECRET`.

</code_context>

<specifics>
## Specific Ideas

- Tenacity replacement is project-wide, not Amadeus-only — closes the hand-rolled retry side-quest while we're in this layer.
- pybreaker chosen over hand-rolled breaker — battle-tested, ~one decorator call.
- Mock auto-fallback is friendly-by-default: missing creds = working dev stack with WARN log + visible flight_provider field, not a startup crash.

</specifics>

<deferred>
## Deferred Ideas

- **Cross-vendor flight clients (Skyscanner, Google):** vendor-neutral contract already supports them; ship Amadeus first, additional providers in v2.
- **In-process result caching with TTL:** pure passthrough for v1; revisit if Amadeus rate limits bite.
- **Aggressive retry tuning (jitter, `Retry-After` header parsing):** Phase 8 (production hardening) — once we have real traffic patterns.
- **Settings-driven circuit breaker thresholds (vs hardcoded):** Phase 8 if needed.
- **Rate limiting (`slowapi`):** explicitly out of scope per ADR-009.
- **Raw vendor payload exposure for diagnostics:** rejected — contract is the only output. Structured logs (Phase 8) carry diagnostics.

</deferred>

---

*Phase: 7-Real Flight API*
*Context gathered: 2026-06-05*
