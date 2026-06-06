---
status: partial
phase: 07-real-flight-api
source: [07-VERIFICATION.md]
started: 2026-06-06
updated: 2026-06-06
---

## Current Test

[awaiting human testing]

## Tests

### 1. Run `just test-duffel` with a real DUFFEL_API_TOKEN against the Duffel sandbox
expected: All four e2e_duffel tests (test_auth_probe, test_real_search_returns_results, test_vendor_neutral_shape, test_error_mapping_401_with_bogus_token) pass live; MAD→BCN search returns ≥1 offer (Pitfall 1 fallback to LON→NYC if sandbox sparse)
result: [pending]

### 2. Verify Duffel-specific tokens are redacted in real log output
expected: Generating a log line containing a duffel_test_<20+chars> or duffel_live_<20+chars> token through the application logger surfaces 'duffel_[REDACTED]' rather than the live token
result: [pending]

### 3. Verify CI duffel-e2e job actually runs when an admin sets vars.DUFFEL_E2E_ENABLED=true and secrets.DUFFEL_API_TOKEN
expected: Job becomes active on next push, runs the four-test suite live, all tests pass; PR CI from forks remains unaffected
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
