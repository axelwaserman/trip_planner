# Phase 7: Real Flight API - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Note:** Phase 7 was previously planned + shipped against Amadeus (07-01..07-07, 25/25 truths verified). Amadeus closed self-service signups, so the Amadeus integration was removed wholesale (see commit `5d7499c`) and Phase 7 is being re-planned around **Duffel**. Vendor-agnostic plumbing (`tenacity` retry, `pybreaker` circuit breaker, `pyreqwest`, `FlightAPIClient` ABC + Mock, lifespan auto-fallback shape, `/health flight_provider` field, `APIError` hierarchy, vendor-neutral `Flight` shape from Phase 4.6) is preserved and reused.

<domain>
## Phase Boundary

Replace the `MockFlightAPIClient` (default in dev/test) with a real **Duffel** client behind the existing `FlightAPIClient` ABC. Outbound HTTP via `pyreqwest` (ADR-008). The vendor-neutral `Flight` / `FlightSegment` / `FlightResult` shape from Phase 4.6 is the canonical normalization target. Mock client remains the test default via DI override. Real-API tests are gated on `DUFFEL_API_TOKEN` + repository variable.

In scope:
- `DuffelFlightClient` implementation of `FlightAPIClient` (search, health_check, get_flight_details, check_availability)
- Single-round-trip search via `POST /air/offer_requests` with `return_offers=true` — read embedded `data.offers[]`
- Vendor-specific `_normalize_offer` as a private method on `DuffelFlightClient` mapping Duffel `offer.slices[].segments[]` → vendor-neutral `Flight` (multi-segment, ISO-8601 with attached UTC, price, IATA, carriers, booking_class)
- `Settings.duffel_api_token: SecretStr | None` + `Settings.duffel_env: Literal["test", "live", "mock"] = "test"`
- Lifespan auto-fallback: `duffel_env == "mock"` OR `duffel_api_token is None` → `MockFlightAPIClient`
- `Duffel-Version: v2` hardcoded as module constant in `duffel_client.py`
- HTTP-status-driven error mapping via reused `_raise_from_http_status` shape
- `FlightQuery.return_date: date | None = None` (backend round-trip support; frontend rendering deferred)
- Strip per-vendor module-level normalizers from `flight_search.py` (`normalize_amadeus_offer`, `normalize_skyscanner_itinerary`) — normalization moves onto each `FlightAPIClient` impl
- Real-API tests in `backend/tests/e2e_duffel/` with dedicated `duffel-e2e` CI job gated on `secrets.DUFFEL_API_TOKEN` + `vars.DUFFEL_E2E_ENABLED == 'true'`
- `just test-duffel` target + README credential setup section

Out of scope (deferred):
- OAuth2 / token-cache / `_refresh_token` (Duffel uses static bearer token — none of that applies)
- Cursor pagination beyond first batch (single round trip; `offset > 0` returns first `limit`)
- Per-passenger-type counts (adult-only first cut; `FlightQuery.passengers: int` maps to `[{"type": "adult"}] * n`)
- Frontend rendering of return-leg results (round-trip backend lands; UI updates deferred)
- Airport-IATA-to-timezone lookup (naive datetimes get UTC attached; documented limitation)
- Rate limiting (per ADR-009)
- Cross-vendor live clients (Skyscanner, Google) — vendor-neutral contract designed for them already
- In-process result caching with TTL (passthrough only)

</domain>

<decisions>
## Implementation Decisions

### Auth + Settings + error mapping
- **D-01:** `Settings.duffel_api_token: SecretStr | None = None` + `Settings.duffel_env: Literal["test", "live", "mock"] = "test"`. Token type-narrowed by Literal (T-07-01-class mitigation reused), `SecretStr` scrubs in logs (T-07-02). `mock` literal forces `MockFlightAPIClient` even when token is present (useful for tests with real creds in env). Lifespan reads `duffel_api_token.get_secret_value()` only at the point of construction.
- **D-02:** Lifespan auto-fallback: `duffel_env == "mock"` OR `duffel_api_token is None` → `MockFlightAPIClient(seed=42)`. Missing-token path emits exactly one WARN: `DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient`. Boot must NEVER fail because of missing creds — a developer with no Duffel account still gets a working stack. `flight_provider` on `app.state` is `"real"` only when `DuffelFlightClient` is constructed.
- **D-03:** `Duffel-Version` header is hardcoded as `_DUFFEL_VERSION = "v2"` module constant in `app/flights/duffel_client.py`. Attached to every pyreqwest request via `.header("Duffel-Version", _DUFFEL_VERSION)`. Treat as part of the client contract — bumping the version is a code change, not a config change. Matches CLAUDE.md rule: JSON keys / MIME types / wire-version constants live as module-level constants, NOT on `Settings`.
- **D-04:** Error mapping is HTTP-status-driven, NOT Duffel-error-type-driven. Reuse the `_raise_from_http_status(status, exc)` helper shape from the previous Amadeus client: 401 → `APIClientError(retryable=False)`, 422 → `APIClientError(retryable=False)`, 429 → `APIRateLimitError(retryable=True)` with `retry_after` parsed from the `Retry-After` response header (if present), 5xx → `APIServerError(retryable=True)`, other 4xx → `APIClientError(retryable=False)`. Message uses `errors[0].title` ONLY — never `errors[0].detail` (T-07-02-class mitigation: `detail` may echo creds / PII). Duffel `error.type` / `error.code` are logged for diagnostics but do NOT drive retry decisions.

### Search flow + pagination
- **D-05:** Single round trip. `DuffelFlightClient.search` issues `POST /air/offer_requests` with `return_offers=true` (Duffel default) and reads `data.offers[]` from the response. No follow-up `GET /air/offers` call. Up to ~50 offers per request. Acceptable trade-off: caller cannot paginate beyond the first batch — fits the ABC contract `limit: int = 20` exactly.
- **D-06:** `offset` is honored but capped: `DuffelFlightClient.search` returns `offers[:limit]` regardless of the caller's `offset` argument. The ABC signature retains `offset` for vendor-portable callers; `DuffelFlightClient` documents in its docstring that Duffel's single-round-trip flow does not support `offset > 0` and returns the head of the list. This avoids the entire CR-01-class double-application bug (the Amadeus phase shipped a regression on this very point).
- **D-07:** Add `FlightQuery.return_date: date | None = None`. When `None`: send one outbound slice; when set: send two slices (outbound + return). Backend round-trip support end-to-end (FlightQuery + validators, `_normalize_offer`, `search_flights` LangChain tool, Duffel slice construction). Frontend `ToolExecutionCard` rendering of return-leg results is deferred to a future phase. PROJECT.md "Out of Scope" entry for round-trip is updated to drop the exclusion (backend) and tighten it to "frontend rendering of return-leg results".

### Vendor-neutral mapping
- **D-08:** Normalization moves OFF `flight_search.py` and ONTO each `FlightAPIClient` implementation. `DuffelFlightClient._normalize_offer(self, raw: dict) -> Flight` is a private method on the client class. The ABC stays clean — `search()` returns `list[Flight]`, normalization is an implementation detail. `flight_search.py` becomes thin: it owns the `search_flights` LangChain tool entry point and the vendor-neutral `FlightResult` model only. The unused `normalize_amadeus_offer` and `normalize_skyscanner_itinerary` module-level functions are deleted along with their tests/fixtures (no live caller; REQ-tool-json-output multi-vendor proof now lives in `DuffelFlightClient._normalize_offer` + its unit tests against the vendor-neutral contract).
- **D-09:** Naive datetimes from Duffel (`departing_at`, `arriving_at` are ISO-8601 LOCAL strings without TZ offset) get UTC attached: parse via `datetime.fromisoformat`, then `dt.replace(tzinfo=UTC)` if `dt.tzinfo is None`. Mirrors the Pitfall 2 mitigation from the previous Amadeus phase. Documented limitation: timestamps shown in UTC, not local airport time. Airport-IATA-to-timezone lookup deferred (no IATA→TZ table bundled).
- **D-10:** `BookingClass = Literal["economy", "premium_economy", "business", "first"]` (existing in `app/flights/models.py`) maps 1:1 to Duffel `cabin_class`. `FlightQuery.booking_class` passes through unchanged into the Duffel request body; `_normalize_offer` reads `offer.cabin_class` (or `offer.slices[0].segments[0].passengers[0].cabin_class` if the per-segment field is present) into `Flight.booking_class`. Stays a Literal, not a `StrEnum` — single-module taxonomy, CLAUDE.md StrEnum rule does not bite.

### Test gating + search params shape
- **D-11:** Real-API tests live in `backend/tests/e2e_duffel/` (path-isolated). Module-level `pytestmark = pytest.mark.skipif(not DUFFEL_AVAILABLE, ...)` skips the whole suite when `DUFFEL_API_TOKEN` is unset. Default selectors (`pytest`, `just test`, `just test-unit`, `just test-integration`, `just test-e2e`) do NOT collect this directory. New `just test-duffel` target. New CI job `duffel-e2e` in `.github/workflows/ci.yml` gated on BOTH `secrets.DUFFEL_API_TOKEN` AND repository variable `vars.DUFFEL_E2E_ENABLED == 'true'`. PR CI never requires keys. README credential-setup section documents the env vars for local + CI use.
- **D-12:** Live e2e_duffel suite asserts: (a) auth probe — first request with valid token returns 2xx; (b) live search MAD→BCN returns ≥1 offer (LON→NYC fallback if MAD→BCN sandbox is sparse, per the Pitfall 1 carry-over); (c) full vendor-neutral `Flight` shape after `_normalize_offer` (multi-segment when applicable, layovers, price, IATA, ISO-8601 with TZ, carriers, count); (d) 401 with bogus token surfaces as `APIClientError(retryable=False)`. Four tests, mirroring the proven shape of the previous e2e_amadeus suite minus the token-cache test (no token cache exists in the Duffel client).
- **D-13:** Adult-only passengers for v1. `FlightQuery.passengers: int = 1` (existing) is preserved; `DuffelFlightClient` maps it to Duffel `passengers: [{"type": "adult"}] * n`. Children/infants out of scope per PROJECT.md, deferred to a future phase. ChatService prompt + tool schema + frontend rendering all unchanged.
- **D-14:** `FlightQuery.max_stops` (existing) is forwarded server-side to Duffel as `slice.max_connections`. When `max_stops is None`, the field is omitted from each slice. Server-side filtering at the vendor reduces wire bytes. Other filters (`max_price`, `max_duration`) remain client-side via `_apply_filters` because Duffel does not expose those.

### Claude's Discretion
- Exact pyreqwest request-builder chain shape (`.post(url).bearer_auth(token).header(...).json(body).build().send()` vs equivalent variants) — pattern-match the previous Amadeus client's chain shape.
- Module layout: `backend/app/flights/duffel_client.py` (mirrors the now-deleted `amadeus_client.py` location).
- Whether the auth-probe e2e test issues a real `POST /air/offer_requests` or hits a cheaper endpoint (e.g. `/air/airlines` or similar) — researcher confirms the lightest-weight endpoint that proves auth.
- Log scrubber pattern for the bearer token — bearer tokens look like `duffel_test_` / `duffel_live_` prefixes; the existing `ApiKeyScrubber` log filter should already cover them, but verify.
- Whether `health_check()` issues a network call against Duffel or just returns `True` (existing Amadeus health_check pattern).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project specs + ADRs
- `.planning/REQUIREMENTS.md` §REQ-real-flight-api — phase requirement (Duffel, pyreqwest, retry+breaker reuse, mock as test default, gated CI)
- `.planning/REQUIREMENTS.md` §REQ-tool-json-output — Phase 4.6 vendor-neutral contract `DuffelFlightClient._normalize_offer` must satisfy
- `.planning/ROADMAP.md` §"Phase 7: Real Flight API" — goal + 4 success criteria (rewritten for Duffel)
- `ARCHITECTURE.md` ADR-008 — `pyreqwest` mandate for outbound HTTP (forbids `aiohttp`/`httpx`/`requests`)
- `ARCHITECTURE.md` ADR-009 — no rate limiting in v1
- `.planning/PROJECT.md` "Out of Scope" — round-trip / multi-leg currently listed; D-07 narrows it to "frontend rendering of return-leg results"
- `.planning/phases/04.6-vendor-neutral-tool-json/04.6-CONTEXT.md` — vendor-neutral JSON contract (`Flight`, `FlightSegment`, `FlightResult`, `BookingClass`, `SortBy`)
- `.planning/phases/04.7-error-handling-streamevent-hierarchy/04.7-CONTEXT.md` — `StreamEvent` error path the breaker/retry surface emits into

### Existing code (must read before implementing)
- `backend/app/tools/flight_client.py` — `FlightAPIClient` ABC (`search`, `health_check`, `get_flight_details`, `check_availability` signatures); `MockFlightAPIClient` (test default + auto-fallback target)
- `backend/app/tools/flight_search.py` — `search_flights` LangChain tool that consumes `FlightAPIClient`; D-08 deletes the per-vendor module-level normalizers and keeps the tool entry-point + `FlightResult` model
- `backend/app/tools/retry.py` — `retry_on_failure` (tenacity wrapper) — preserved verbatim
- `backend/app/tools/circuit_breaker.py` — `call_with_breaker` (async-safe pybreaker helper) — preserved verbatim
- `backend/app/exceptions.py` — `APIError` / `APITimeoutError` / `APIRateLimitError` / `APIServerError` / `APIClientError` / `FlightSearchError`; `retryable` flag semantics
- `backend/app/flights/models.py` — `Flight`, `FlightSegment`, `FlightQuery`, `FlightResult`, `FlightSearchResult`, `BookingClass`, `SortBy` (vendor-neutral target shapes); D-07 adds `FlightQuery.return_date`
- `backend/app/config.py` — `Settings` (where `duffel_api_token` + `duffel_env` go); the now-deleted Amadeus fields lived here previously, mirror their shape
- `backend/app/api/main.py::lifespan` — auto-fallback decision happens here; lifespan currently constructs `MockFlightAPIClient` unconditionally (post-Amadeus removal). D-02 reintroduces the env+creds branch.
- `backend/app/llm/log_scrubbing.py::ApiKeyScrubber` — log filter that scrubs API-key-like substrings; verify Duffel bearer-token format is covered

### Vendor docs (researcher confirms)
- Duffel API v2 docs: `https://duffel.com/docs/api` (root) — researcher locates exact paths for `/air/offer_requests`, `/air/offers`, error envelope, rate limits, `Retry-After` semantics
- Duffel auth: bearer token in `Authorization: Bearer duffel_test_...` / `duffel_live_...`; `Duffel-Version: v2` header required on every request; `Accept: application/json` required
- Duffel base URL: `https://api.duffel.com` (single base — `_test` vs `_live` token determines sandbox vs production)
- pyreqwest: `https://github.com/messense/pyreqwest` (existing dep — reuse Amadeus-phase patterns)
- tenacity: `https://tenacity.readthedocs.io/` (existing dep)
- pybreaker: `https://github.com/danielfm/pybreaker` (existing dep)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FlightAPIClient` ABC (`backend/app/tools/flight_client.py:13`) — abstract surface; `DuffelFlightClient` implements it.
- `MockFlightAPIClient` — auto-fallback target and unit/integration test default.
- `APIError` hierarchy with `retryable` flag — drives tenacity retry decisions; `_raise_from_http_status` maps Duffel HTTP status codes onto these.
- `Flight`, `FlightSegment`, `FlightQuery`, `FlightResult`, `FlightSearchResult` (`backend/app/flights/models.py`) — already vendor-neutral; mapping target.
- `retry_on_failure` (tenacity, `backend/app/tools/retry.py`) — preserved verbatim from previous Phase 7; reraise=True regression-locked.
- `call_with_breaker` (pybreaker, `backend/app/tools/circuit_breaker.py`) — async-safe; preserved verbatim.
- `ApiKeyScrubber` (`backend/app/llm/log_scrubbing.py`) — log filter; verify it covers `duffel_test_` / `duffel_live_` prefixes.
- DI seam from Phase 5/6 — `FlightAPIClient` provided via `app.state.flight_client`; `DuffelFlightClient` slots in without route-layer changes.

### Established Patterns
- ABC + concrete impl (mirrors Phase 6's `MessageStore`/`PostgresMessageStore` and the now-deleted `FlightAPIClient`/`AmadeusFlightClient` pair).
- `pyreqwest` for outbound HTTP — no `aiohttp`, no `httpx`, no `requests`.
- Async I/O end-to-end; no sync calls in async paths.
- `Settings`-driven env selection — lifespan branches on `Settings.*`.
- Lifespan singleton construction; clients stashed on `app.state`.
- `_raise_from_http_status` shape — single helper maps HTTP codes to `APIError` subclasses; vendor clients use a `try/except StatusError` chain that delegates to it.
- `error_for_status(True)` on every pyreqwest builder so non-2xx raises `StatusError` instead of returning a body the parser chokes on.
- Module-level constants for wire-version / JSON keys / MIME types — NOT on `Settings`.

### Integration Points
- Lifespan (`backend/app/api/main.py::lifespan`) — branch on `duffel_env` + token presence; construct either `DuffelFlightClient(...)` or `MockFlightAPIClient()`; stash on `app.state.flight_client`. Currently constructs Mock unconditionally (post-Amadeus reset).
- `search_flights` LangChain tool — already consumes `FlightAPIClient` via DI; signature unchanged.
- `Settings` — add `duffel_api_token`, `duffel_env`.
- `/health` endpoint — `flight_provider` field already surfaced (preserved from previous Phase 7 D-06); lifespan sets `app.state.flight_provider = "real" | "mock"`.
- CI — new `duffel-e2e` job in `.github/workflows/ci.yml`, gated on `secrets.DUFFEL_API_TOKEN` AND `vars.DUFFEL_E2E_ENABLED == 'true'`.
- `flight_search.py` — D-08 deletes `normalize_amadeus_offer` + `normalize_skyscanner_itinerary` (no live callers); keeps `search_flights` tool entry point and `FlightResult` shape.

</code_context>

<specifics>
## Specific Ideas

- Duffel auth shape is dramatically simpler than Amadeus's OAuth2 client_credentials flow — no token cache, no `_refresh_token`, no `asyncio.Lock` around concurrent refresh, no proactive expiry check, no malformed-body guard for token responses. The entire Amadeus token-cache layer (D-01..D-03 from the previous phase, plus the CR-02 gap-closure) does not apply.
- Duffel `Duffel-Version: v2` header is mandatory; missing it returns `400 Bad Request` per Duffel docs. Hardcode as a module constant per CLAUDE.md.
- Duffel error envelope `{errors: [{type, code, title, detail, source}], meta}` is more granular than Amadeus's. The HTTP-status-driven mapping (D-04) intentionally ignores `error.type` for retry decisions to keep the mapping vendor-portable.
- The previously-shipped Amadeus phase achieved 25/25 verification truths but was deleted along with vendor self-service access. The vendor-agnostic plumbing (retry, breaker, pyreqwest patterns, lifespan branch shape, /health field, ABC) is preserved and provides a strong template — the Duffel phase is a smaller delta than starting from scratch.

</specifics>

<deferred>
## Deferred Ideas

- **Cursor pagination beyond first batch** — Duffel exposes `GET /air/offers?offer_request_id=...&limit=...&after=...` for cursors; v1 single-round-trip ignores it. If user-driven pagination becomes a real need, revisit (would require ABC shape change or a second round trip).
- **Per-passenger-type counts (children, infants)** — `FlightQuery.passengers: int` stays. Adding `adults`/`children`/`infants` would extend the LLM tool schema and frontend; out of scope per PROJECT.md.
- **Frontend rendering of return-leg results** — D-07 adds backend round-trip support; ToolExecutionCard does not render return legs. Future phase.
- **Airport-IATA-to-timezone lookup** — naive datetimes get UTC attached (D-09); proper local-time rendering needs an IATA→TZ table (e.g. `airportsdata` ~250kB or local fixture). Defer.
- **Cross-vendor live clients (Skyscanner, Google, Kayak, ...)** — vendor-neutral `Flight` shape + `_normalize_offer` per-impl pattern (D-08) is designed to absorb additional providers; ship Duffel only for v1.
- **In-process result caching with TTL** — passthrough only.
- **Aggressive retry tuning** (jitter, full `Retry-After` parsing, request-id correlation) — Phase 8 (production hardening).
- **Settings-driven circuit breaker thresholds** — hardcoded for v1.
- **Rate limiting (`slowapi`)** — explicitly out of scope per ADR-009.
- **Raw vendor payload exposure for diagnostics** — rejected. Vendor-neutral `Flight` is the only output. Structured logs (Phase 8) carry diagnostics.

</deferred>

---

*Phase: 7-Real Flight API*
*Context gathered: 2026-06-06*
