---
status: partial
phase: 07-real-flight-api
source: [07-VERIFICATION.md]
started: 2026-06-05T12:00:00Z
updated: 2026-06-05T12:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Real Amadeus sandbox token fetch + search end-to-end
expected: With AMADEUS_API_KEY + AMADEUS_API_SECRET set, `just test-amadeus` runs all four e2e_amadeus tests and they pass against the live sandbox: token fetched, MAD→BCN search returns ≥1 result, vendor-neutral fields populated, bad-credentials path raises APIClientError with retryable=False (newly tightened by Plan 07-07).
result: [pending]

### 2. /health surfaces flight_provider='real' under real credentials
expected: With AMADEUS_API_KEY + AMADEUS_API_SECRET set in the running shell, `curl http://localhost:8000/health` returns `{"status":"healthy","flight_provider":"real"}` (currently grep-verified in mock fallback only).
result: [pending]

### 3. WARN log line emits exactly when AMADEUS_ENV is non-mock and creds are missing
expected: Booting the backend with AMADEUS_ENV=test and no AMADEUS_API_KEY / AMADEUS_API_SECRET emits exactly one WARN containing the substring `AMADEUS_* creds missing`. Asserted programmatically by tests/integration/test_lifespan_flight_provider.py via caplog, but the human should sanity-check that it appears in the actual app output too.
result: [pending]

### 4. Pitfall 1 — sandbox sparse routes
expected: MAD→BCN returns ≥1 offer in the live sandbox; if it does not, swap to LON→NYC per Plan 06 output guidance.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
