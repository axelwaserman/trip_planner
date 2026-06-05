# Phase 7: Real Flight API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 7-real-flight-api
**Areas discussed:** Auth + token lifecycle, Endpoint env + mock fallback, Field mapping coverage, Retry + circuit breaker, Test gating

---

## Auth — Amadeus token cache strategy

| Option | Description | Selected |
|--------|-------------|----------|
| In-process cache, refresh on 401 | Cache token in memory; refresh on 401. Simple. | |
| In-process with proactive refresh | Cache token + expiry; refresh ~60s before expiry. No 401 latency hit. | ✓ |
| Per-request fetch (no cache) | Fetch token before every search call. Doubles latency. | |

**User's choice:** In-process with proactive refresh
**Notes:** Implementation refined in follow-up to **inline-on-call with concurrent-refresh lock** (asyncio.Lock so concurrent requests don't trigger duplicate refreshes). No background lifespan task.

---

## Endpoint env + mock fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Settings flag + auto-fallback | `Settings.amadeus_env = 'test' \| 'prod' \| 'mock'`. Auto-fallback to Mock if creds missing. WARN log. | ✓ |
| Strict env-driven, no auto-fallback | Startup fails if creds missing and env != 'mock'. | |
| Always real if any creds, else mock | Implicit selection by cred presence; no flag. | |

**User's choice:** Settings flag + auto-fallback
**Notes:** Visibility refined to: WARN log on fallback **plus** healthcheck endpoint reports `flight_provider: 'real' | 'mock'`.

---

## Field mapping coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Full Phase 4.6 contract incl. multi-segment + layovers | Full mapping (segments[], carriers, price, IATA, ISO times). Baggage/fare-class best-effort. | ✓ |
| Minimum viable: price + endpoints + times | Only essentials; segments[] empty. | |
| Full contract + raw payload escape hatch | Full mapping + raw Amadeus payload in debug field. | |

**User's choice:** Full Phase 4.6 contract incl. multi-segment + layovers
**Notes:** Best-effort fields (terminal, fare class, baggage) omitted when missing — never stubbed. No raw payload escape hatch.

---

## Retry mechanism (tenacity scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Replace existing decorator project-wide | Delete `backend/app/tools/retry.py`, swap callers to tenacity. | ✓ |
| Wrap Amadeus client only | Add tenacity for Amadeus methods only; existing decorator stays. | |
| Replace decorator, scoped to retry.py module | Reimplement retry.py as tenacity wrapper preserving public API. | |

**User's choice:** Replace existing decorator project-wide
**Notes:** Practical interpretation = reimplement `retry.py` as a thin tenacity wrapper that preserves the existing public API (`max_retries`, `backoff_base`, `exceptions`) so callers don't change. Closes hand-rolled retry side-quest.

---

## Circuit breaker

| Option | Description | Selected |
|--------|-------------|----------|
| Add purgatory or pybreaker library | Compose tenacity (retry) + pybreaker (breaker). | ✓ |
| Skip circuit breaker for v1 | Tenacity retry only. Defer breaker to Phase 8. | |
| Hand-rolled minimal breaker | ~30-line consecutive-failure counter on the client. | |

**User's choice:** pybreaker
**Notes:** Compose: tenacity wraps inner HTTP call, pybreaker wraps full retry block. Defaults: 5 consecutive failures → open, 60s reset.

---

## Retry tuning for Amadeus

| Option | Description | Selected |
|--------|-------------|----------|
| Tight tuning: 2 retries, jitter, honor Retry-After | Conservative for Amadeus test tier. | |
| Defaults: 3 retries, exponential, no Retry-After | Tenacity defaults; Phase 8 tunes if needed. | ✓ |

**User's choice:** Defaults
**Notes:** Map Amadeus 429 + 5xx → retryable; 4xx (non-429) → non-retryable.

---

## Proactive token refresh — implementation

| Option | Description | Selected |
|--------|-------------|----------|
| Refresh on first call after expiry threshold | Inline check on each call; no lifespan task. | |
| Lifespan background task | asyncio.create_task in lifespan refreshes ahead. | |
| Inline-on-call with concurrent-refresh lock | Inline + asyncio.Lock to dedupe concurrent refresh. | ✓ |

**User's choice:** Inline-on-call with concurrent-refresh lock

---

## Mock auto-fallback — visibility

| Option | Description | Selected |
|--------|-------------|----------|
| WARN log + healthcheck reports 'mock' | Log on lifespan + `/healthz` surfaces choice. | ✓ |
| WARN log only | No API surface; rely on logs. | |

**User's choice:** WARN log + healthcheck reports 'mock'

---

## Real-API integration test gating

| Option | Description | Selected |
|--------|-------------|----------|
| pytest fixture skip when AMADEUS_* missing | Skip in fixture; tests live alongside others. | |
| Separate tests/e2e_amadeus/ + dedicated CI job | Isolated dir + dedicated CI workflow. | ✓ |

**User's choice:** Separate `backend/tests/e2e_amadeus/` + dedicated CI job
**Notes:** Default `pytest`, `just test*` recipes never run them. PR CI never requires keys.

---

## Claude's Discretion

- Exact tenacity API surface (`@retry` decorator vs `Retrying` class) — pick whatever maps cleanly onto current `retry_on_failure` signature.
- Module layout: `backend/app/flights/amadeus_client.py` or similar — pattern-match Phase 6's `MessageStore`/`PostgresMessageStore` split.
- Whether circuit-breaker thresholds are Settings-driven or hardcoded for v1 — lean hardcoded, revisit Phase 8.
- Healthcheck endpoint placement — extend existing if present, else add minimal endpoint.

## Deferred Ideas

- Cross-vendor flight clients (Skyscanner, Google) — v2.
- In-process result caching with TTL — revisit if rate limits bite.
- Aggressive retry tuning (jitter, Retry-After parsing) — Phase 8.
- Settings-driven breaker thresholds — Phase 8 if needed.
- Rate limiting — out of scope per ADR-009.
- Raw vendor payload exposure — rejected; contract is the only output.
