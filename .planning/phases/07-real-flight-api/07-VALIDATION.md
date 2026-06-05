---
phase: 07
slug: real-flight-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `07-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (auto mode) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && uv run pytest tests/unit/ -x --tb=short` |
| **Full suite command** | `cd backend && uv run pytest tests/unit tests/integration --cov=app --cov-fail-under=60` |
| **Amadeus real-API suite** | `cd backend && uv run pytest tests/e2e_amadeus/ -v -s` (gated on `AMADEUS_*` secrets) |
| **Estimated runtime** | quick ~5s · full ~60s · e2e_amadeus ~30s (network) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/unit/ -x --tb=short`
- **After every plan wave:** Run `cd backend && uv run pytest tests/unit tests/integration --cov=app --cov-fail-under=60`
- **Before `/gsd:verify-work`:** Full unit + integration suite must be green; `e2e_amadeus` runs separately under CI job gated on `AMADEUS_*` secrets
- **Max feedback latency:** ~10s (per-task quick run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | REQ-real-flight-api | — | tenacity-backed `retry_on_failure` preserves public API; `RetryError` does not escape (`reraise=True`) | unit | `cd backend && uv run pytest tests/unit/test_retry.py -x` | ✅ exists (update) | ⬜ pending |
| 07-02-01 | 02 | 1 | REQ-real-flight-api | — | normalize Amadeus offer → vendor-neutral `Flight` (UTC TZ on naive `departure.at`) | unit | `cd backend && uv run pytest tests/unit/test_amadeus_client.py -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | REQ-real-flight-api | T-07-02 (cred leakage) | concurrent callers share single token refresh under `asyncio.Lock`; `SecretStr` for creds | unit | `cd backend && uv run pytest tests/unit/test_amadeus_token_cache.py -x` | ❌ W0 | ⬜ pending |
| 07-02-03 | 02 | 1 | REQ-real-flight-api | — | pybreaker async-safe `_call_with_breaker` trips at `fail_max`; `CircuitBreakerError` → `APIError` | unit | `cd backend && uv run pytest tests/unit/test_circuit_breaker.py -x` | ❌ W0 | ⬜ pending |
| 07-02-04 | 02 | 1 | REQ-real-flight-api | — | HTTP 401→APIClientError, 429→APIRateLimitError(retryable), 5xx→APIServerError(retryable), 4xx→APIClientError | unit | `cd backend && uv run pytest tests/unit/test_amadeus_error_mapping.py -x` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | REQ-real-flight-api | T-07-01 (SSRF), T-07-02 | lifespan branches on `amadeus_env` + cred presence; missing creds → MockFlightAPIClient + WARN log; no creds in logs | integration | `cd backend && uv run pytest tests/integration/test_health.py -x` | ✅ exists (extend) | ⬜ pending |
| 07-03-02 | 03 | 2 | REQ-real-flight-api | — | `/healthz` returns `flight_provider: "real" \| "mock"` | integration | `cd backend && uv run pytest tests/integration/test_health.py::test_health_includes_flight_provider -x` | ❌ W0 | ⬜ pending |
| 07-04-01 | 04 | 3 | REQ-real-flight-api | — | real OAuth token fetch + cache hit | e2e_amadeus | `cd backend && uv run pytest tests/e2e_amadeus/test_amadeus_client.py::test_token_fetch_and_cache` | ❌ W0 | ⬜ pending |
| 07-04-02 | 04 | 3 | REQ-real-flight-api | — | real search MAD→BCN returns ≥1 result | e2e_amadeus | `cd backend && uv run pytest tests/e2e_amadeus/test_amadeus_client.py::test_real_search_returns_results` | ❌ W0 | ⬜ pending |
| 07-04-03 | 04 | 3 | REQ-real-flight-api | — | full vendor-neutral shape after real normalization (multi-segment + carriers + price) | e2e_amadeus | `cd backend && uv run pytest tests/e2e_amadeus/test_amadeus_client.py::test_vendor_neutral_shape` | ❌ W0 | ⬜ pending |
| 07-05-01 | 05 | 3 | REQ-real-flight-api | — | CI workflow runs `e2e_amadeus` only when `secrets.AMADEUS_API_KEY` set; PR CI never requires keys | manual | n/a (workflow file inspection) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_amadeus_client.py` — unit tests for normalize/map/error-mapping (no real HTTP)
- [ ] `tests/unit/test_amadeus_token_cache.py` — concurrent token refresh with `asyncio.Lock`
- [ ] `tests/unit/test_circuit_breaker.py` — pybreaker async-safe pattern: `_call_with_breaker` trips at `fail_max`
- [ ] `tests/unit/test_amadeus_error_mapping.py` — Amadeus HTTP status → APIError subclass mapping
- [ ] `tests/integration/test_health.py::test_health_includes_flight_provider` — extend existing
- [ ] `tests/e2e_amadeus/__init__.py` + `tests/e2e_amadeus/conftest.py` + `tests/e2e_amadeus/test_amadeus_client.py` — real-API tests with `pytestmark = pytest.mark.skipif(not AMADEUS_AVAILABLE, ...)` guard
- [ ] Update `tests/unit/test_retry.py` — existing tests must pass unchanged after tenacity replacement; add regression test for `RetryError` not escaping (`reraise=True`)
- [ ] `justfile` — new target `test-amadeus` invoking `cd backend && uv run pytest tests/e2e_amadeus/ -v`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI gating: `e2e_amadeus` job only runs with secrets present | REQ-real-flight-api | GitHub Actions secret presence cannot be asserted from unit tests | Inspect `.github/workflows/*.yml`; confirm `if: ${{ secrets.AMADEUS_API_KEY != '' }}` (or equivalent) on the e2e_amadeus job; confirm PR CI default workflow does not include this job |
| Documentation describes credential setup | REQ-real-flight-api §SC-4 | Doc-quality check | Read `README.md` / `docs/` for AMADEUS_* env-var setup (local + CI) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
