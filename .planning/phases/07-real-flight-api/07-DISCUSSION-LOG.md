# Phase 7: Real Flight API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 07-real-flight-api
**Areas discussed:** Auth + Settings + error mapping; Search flow + pagination; Vendor-neutral mapping; Test gating + search params shape

---

## Auth + Settings + error mapping

### Q1 — Settings shape

| Option | Description | Selected |
|--------|-------------|----------|
| Single token + explicit env flag | `duffel_api_token: SecretStr | None = None` + `duffel_env: Literal["test","live","mock"] = "test"`. Mirrors old D-04/D-05 shape. SecretStr scrubs in logs; `mock` forces mock client even with token present. | ✓ |
| Single token only (derive env from prefix) | `duffel_api_token: SecretStr | None = None`. Lifespan inspects token prefix (`duffel_test_` / `duffel_live_`). Simpler config; loses explicit `mock` override. | |
| Token + env + base_url override | Plus `duffel_base_url: str | None = None` for self-hosted/proxy edge cases. Overkill for v1. | |

**User's choice:** Single token + explicit env flag.
**Notes:** Mirrors the proven shape from the previous Amadeus phase. → D-01.

### Q2 — Mock-fallback trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Same shape: env=='mock' OR token missing | `duffel_env=='mock' OR duffel_api_token is None` → MockFlightAPIClient. Missing-token path logs WARN. Boot never fails. Mirrors D-05 from previous Amadeus phase. | ✓ |
| Token-only trigger | Just `duffel_api_token is None` → Mock. Simpler; loses explicit way to force mock when token IS present. | |

**User's choice:** Same shape (env-or-token).
**Notes:** WARN line `DUFFEL_API_TOKEN missing — falling back to MockFlightAPIClient`. → D-02.

### Q3 — Where `Duffel-Version: v2` lives

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcode in DuffelFlightClient | `_DUFFEL_VERSION = "v2"` module constant. Treat as part of client contract. Matches CLAUDE.md rule (wire constants on module, not Settings). | ✓ |
| `Settings.duffel_api_version: str = "v2"` | Configurable via env. Useful for future v3, but version bumps usually require code changes anyway. | |

**User's choice:** Hardcode as module constant.
**Notes:** → D-03.

### Q4 — Error mapping policy

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP-status-driven | Reuse `_raise_from_http_status` shape. 401/422/4xx → APIClientError(False); 429 → APIRateLimitError(True, Retry-After); 5xx → APIServerError(True). Ignore Duffel error.type for retry. Message uses `errors[0].title` only (T-07-02). | ✓ |
| Duffel-error-type-driven | Branch on `errors[0].type` (rate_limit, authentication_error, etc.). More granular but couples to vendor envelope. | |
| Hybrid: status first, type as tiebreaker | Status decides retryable; type refines APIError subclass. More code, marginal benefit. | |

**User's choice:** HTTP-status-driven.
**Notes:** Vendor-portable; ready for second provider. → D-04.

---

## Search flow + pagination semantics

### Q1 — Round-trip pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Single round trip — read embedded offers | POST `/air/offer_requests` with `return_offers=true`, read `data.offers[]`. One HTTP call. Up to ~50 offers. No cursor state. Fits ABC `limit: int = 20`. | ✓ |
| Two round trips — POST then GET paginated | POST with `return_offers=false`, then GET `/air/offers` with cursors. Full pagination but 2x HTTP per search. | |
| Hybrid — POST + offers, paginate on demand | Embedded as page 1; fall through to GET when offset > 0. Most complex. | |

**User's choice:** Single round trip.
**Notes:** → D-05.

### Q2 — Offset semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Drop offset entirely — always return first `limit` | `DuffelFlightClient.search` ignores offset; returns `data.offers[:limit]`. Documented in docstring. ABC signature preserved for vendor portability. Avoids CR-01-class double-application bug. | ✓ |
| Reject offset > 0 with APIClientError | Loud failure on `offset > 0`. Couples ABC to vendor capability. | |
| Slice post-fetch | Return `offers[offset : offset + limit]`. Same CR-01-class silent-drop hazard. | |

**User's choice:** Drop offset, return first `limit`.
**Notes:** → D-06.

### Q3 — Slices (one-way vs round trip)

| Option | Description | Selected |
|--------|-------------|----------|
| Outbound only (one-way) — single slice | `FlightQuery` already shapes for outbound only. PROJECT.md "Out of Scope" lists round-trip as v2. | |
| Add return_date support — conditional second slice | Extend `FlightQuery` with `return_date`. Bigger surface change. PROJECT.md scope conflict. | ✓ |

**User's choice:** Add return_date support.
**Notes:** Triggered scope-guardrail follow-up Q4.

### Q4 — Scope reconciliation for round-trip

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — expand scope, update PROJECT.md | Backend + frontend both updated. PROJECT.md "Out of Scope" entry removed. Phase grows. | |
| No — keep one-way for v1 | Defer round-trip. Phase 7 ships smaller. | |
| Yes backend, no frontend | Backend supports round trip end-to-end (FlightQuery, normalizer, search_flights, Duffel slices). Frontend rendering deferred. | ✓ |

**User's choice:** Yes backend, no frontend.
**Notes:** PROJECT.md "Out of Scope" narrows to "frontend rendering of return-leg results". → D-07.

---

## Vendor-neutral mapping for Duffel

### Q1 — Where the normalizer lives

| Option | Description | Selected |
|--------|-------------|----------|
| Add normalize_duffel_offer alongside | Three normalizers in `flight_search.py`. Multi-vendor proof from Phase 4.6 preserved. | |
| Rename + drop unused | Rename Amadeus normalizer; delete Skyscanner. Diverges from REQUIREMENTS.md fixtures. | |
| (User free-text) Each FlightAPIClient impl owns its own `_normalize_offer` | Vendor-specific normalization moves OFF `flight_search.py` and ONTO each client. | ✓ |

**User's choice:** Method on the client class — `DuffelFlightClient._normalize_offer`.
**Notes:** Keeps `flight_search.py` thin. Old per-vendor normalizers + their fixtures deleted. REQ-tool-json-output multi-vendor proof now lives in `DuffelFlightClient._normalize_offer` + unit tests against the vendor-neutral contract. → D-08.

### Q2 — Naive datetime handling

| Option | Description | Selected |
|--------|-------------|----------|
| Treat as UTC | Parse + attach UTC if `tzinfo is None`. Mirrors Pitfall 2 mitigation from prior phase. Documented limitation. | ✓ |
| Reject naive datetimes | Loud failure if no TZ. Wrong default — Duffel never returns TZ. | |
| Look up airport TZ from IATA | Correct but heavy. Defer. | |

**User's choice:** Treat as UTC.
**Notes:** → D-09.

### Q3 — BookingClass mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Map 1:1 | Existing `BookingClass = Literal["economy","premium_economy","business","first"]` matches Duffel `cabin_class` exactly. Pass-through. | ✓ |
| Need to check existing values first | Verify before deciding. | |

**User's choice:** Map 1:1.
**Notes:** Verified `app/flights/models.py:20` — values match. Stays a Literal (single-module taxonomy). → D-10.

---

## Test gating + search params shape

### Q1 — Gating pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Same pattern, renamed | `tests/e2e_duffel/` + `pytestmark` + `just test-duffel` + CI `duffel-e2e` job + repository var `DUFFEL_E2E_ENABLED`. Proven shape (D-14/D-15 from prior phase). | ✓ |
| Token-only gate, drop repository variable | Simpler; only valid if no PR triggers. | |

**User's choice:** Same pattern, renamed.
**Notes:** → D-11.

### Q2 — E2E suite assertion targets

| Option | Description | Selected |
|--------|-------------|----------|
| Auth + search + shape + 401 | Drop token-fetch+cache (Duffel has no token cache). Live MAD→BCN ≥1 + vendor-neutral shape + 401 → APIClientError(False). | ✓ |
| Add 422 validation error test | Plus 422 with malformed body. | |
| Minimal — search + 401 only | Two tests. Vendor-neutral shape verified at unit level only. | |

**User's choice:** Auth + search + shape + 401.
**Notes:** Four tests. LON→NYC fallback per Pitfall 1. → D-12.

### Q3 — Passenger types

| Option | Description | Selected |
|--------|-------------|----------|
| Adult-only, derive from `passengers: int` | Map `FlightQuery.passengers` to `[{"type": "adult"}] * n`. Consistent with PROJECT.md scope. | ✓ |
| Add per-type counts (adults/children/infants) | Bigger surface change. Out of scope per PROJECT.md. | |

**User's choice:** Adult-only.
**Notes:** → D-13.

### Q4 — `max_stops` mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Forward `max_stops` → `max_connections` per slice | Server-side filtering at vendor. Less data over the wire. | ✓ |
| Always client-side filter | Don't push to Duffel; filter in `_apply_filters`. More bytes over the wire. | |

**User's choice:** Forward to Duffel.
**Notes:** Other filters (`max_price`, `max_duration`) stay client-side because Duffel doesn't expose them. → D-14.

---

## Claude's Discretion

- Exact pyreqwest request-builder chain shape — pattern-match the prior Amadeus client's chain.
- Module layout — `backend/app/flights/duffel_client.py` (mirrors prior `amadeus_client.py` location).
- Whether the auth-probe e2e test uses `POST /air/offer_requests` or a cheaper endpoint — researcher confirms.
- Log scrubber coverage of `duffel_test_` / `duffel_live_` prefixes — verify against existing `ApiKeyScrubber`.
- Whether `health_check()` issues a network call or returns `True` — pattern-match prior Amadeus client.

## Deferred Ideas

- Cursor pagination beyond first batch.
- Per-passenger-type counts (children, infants).
- Frontend rendering of return-leg results.
- Airport-IATA-to-timezone lookup.
- Cross-vendor live clients (Skyscanner, Google, Kayak, …).
- In-process result caching with TTL.
- Aggressive retry tuning (jitter, full Retry-After parsing).
- Settings-driven circuit-breaker thresholds.
- Rate limiting (per ADR-009).
- Raw vendor payload exposure for diagnostics.
