# Trip Planner: Implementation Plan

> Generated: 2026-05-13
> Last updated: 2026-05-13
> Based on: `.planning/codebase/` analysis + adversarial review + CI/CD plan + skills audit

## Progress

| Phase | Status | Branch | PR |
|-------|--------|--------|----|
| Phase 0: Bug Fixes + Cleanup | ✅ MERGED | `phase-0-bug-fixes-cleanup` | #1 merged to master |
| Phase 1: Auth Hardening | ⏳ TODO | — | — |
| Phase 2: CI/CD Pipeline | ⏳ TODO | — | — |
| Phase 3: Backend Test Coverage | ⏳ TODO (blocks on Phase 1) | — | — |
| Phase 4: Frontend Testing | ⏳ TODO | — | — |
| Phase 5: Security Hardening | ⏳ TODO (blocks on Phase 1) | — | — |
| Phase 6: Coverage 80% | ⏳ TODO (blocks on Phase 3 + Phase 4) | — | — |

## Current State (post Phase 0 merge)

- Base branch: `master` (Phase 0 merged via PR #1)
- 69 tests pass: `uv run pytest -m "not slow"`
- ruff, mypy clean
- `ChatService.__init__` takes explicit `flight_client: FlightAPIClient` + `llm: BaseChatModel`
- `get_session_history` raises `ValueError` for unknown sessions
- `delete_session` cleans up all 3 dicts (`_histories`, `_metadata`, `_last_activity`)

## Next Steps (start in parallel, all branch from `master`)

1. **Phase 2** (1–2 hrs): Create `.github/workflows/ci.yml`
2. **Phase 1** (4–6 hrs): Real JWT auth in `auth.py`, protect chat routes
3. **Phase 4** (6–8 hrs): Vitest, decompose `ChatInterface.tsx`

---

## Executive Summary

- Replace placeholder auth with real JWT (`pyjwt` + `pwdlib` — already installed), apply to all protected routes
- Add GitHub Actions CI: backend (ruff/mypy/pytest @60% coverage) + frontend (eslint/tsc)
- Fix existing bugs: missing `_metadata` deletion, silent `get_session_history`, wrong status code in e2e tests, bad import paths
- Add frontend testing via Vitest, decompose monolithic `ChatInterface.tsx` into testable hooks
- Security hardening: CSP headers, CORS from env, rate limiting, markdown XSS sanitization

---

## Phase Dependency Graph

```
Phase 0 (Bug Fixes + Cleanup)
    |
    ├──> Phase 1 (Auth Hardening)
    |        |
    |        └──> Phase 3 (Backend Test Coverage)
    |                  |
    └──> Phase 2 (CI/CD Pipeline)   └──> Phase 6 (Coverage 80%)
                                              ^
    Phase 4 (Frontend Testing) ───────────────┘
    Phase 5 (Security Hardening) — depends on Phase 1
```

Phases 2 and 4 can start in parallel after Phase 0 merges.

---

## Phase 0: Bug Fixes and Cleanup

**Goal:** Eliminate known bugs and dead code before feature work.
**Effort:** 2–3 hours

### Changes

| File | Change |
|------|--------|
| `backend/app/api/routes/routes.py` lines 164–167 | Add `del chat_service._metadata[session_id]` — currently missing, causing memory leak |
| `backend/app/chat.py` line 31 | Remove duplicate `search_flights._flight_client = flight_client` (also set at `main.py:45`) |
| `backend/app/chat.py` `get_session_history` | Change to raise `ValueError` when session not found (currently returns `None`, making the `try/except ValueError` in routes dead code) |
| `backend/tests/e2e/test_e2e.py` lines 96, 146 | Fix `assert session_response.status_code == 200` → `201` (route declares `HTTP_201_CREATED`) |
| `backend/tests/e2e/test_e2e.py` line 9 | Fix `from backend.app.api.main import app` → `from app.api.main import app` |
| `backend/tests/integration/test_chat.py` line 9 | Same import fix |
| `backend/tests/integration/test_health.py` line 5 | Same import fix |
| `backend/pyproject.toml` | Remove `langgraph>=1.0.2` (installed, unused); add `pytest-cov>=6.0` to dev deps |

### Acceptance Criteria
- `uv run pytest -m "not slow"` passes
- `uv run ruff check . && uv run ruff format --check .` passes
- `uv run mypy app/` passes
- `delete_session` route removes `_metadata[session_id]`
- `get_session_history("nonexistent")` raises `ValueError`
- `langgraph` absent from `uv.lock` after `uv sync`

**Skills:** `everything-claude-code:python-review`

---

## Phase 1: Auth Hardening

**Goal:** Replace fake auth with real JWT. Apply auth dependency to protected routes.
**Effort:** 4–6 hours

**Design decision:** In-memory user store seeded from `AUTH_USERS=user1:pass1,user2:pass2` env var. No registration endpoint. No DB needed.

### Changes

| File | Change |
|------|--------|
| `backend/app/api/routes/auth.py` | Full rewrite: JWT via `pyjwt`, passwords via `pwdlib[argon2]`, `load_users_from_env()`, `/token` returns signed JWT, `get_current_user` decodes JWT |
| `backend/app/config.py` | Add: `jwt_secret: str`, `jwt_algorithm: str = "HS256"`, `jwt_expire_minutes: int = 60`, `auth_users: str = "admin:admin"` |
| `backend/app/api/routes/routes.py` | Add `Depends(get_current_active_user)` to `chat()`, `create_session()`, `get_providers()`. Health check stays public. |
| `backend/tests/conftest.py` | Add `auth_headers` fixture returning valid JWT Bearer token |

### Auth module structure
```
1. UserInDB model with hashed_password field
2. load_users_from_env() -> dict[str, UserInDB]
3. verify_password(plain, hashed) via pwdlib
4. create_access_token(data: dict) -> str via pyjwt
5. get_current_user(token) -> User — decode JWT, lookup user
6. get_current_active_user(user) -> User — check disabled flag
7. POST /token — validate credentials, return JWT
```

### Acceptance Criteria
- `POST /token` with valid credentials returns `{"access_token": "...", "token_type": "bearer"}`
- `POST /api/chat` without Bearer token → 401
- `POST /api/chat` with valid token → succeeds
- `GET /api/providers` requires auth
- `GET /health` does NOT require auth
- Startup warns if `jwt_secret` is default value
- All tests updated with auth headers and pass

**Skills:** `fastapi` (local), `everything-claude-code:tdd`, `everything-claude-code:security-review`

**Known limitation:** No token revocation (no DB = no deny-list). Mitigate with short expiry (60 min).

---

## Phase 2: CI/CD Pipeline

**Goal:** Automated quality gates on every push/PR.
**Effort:** 1–2 hours

### Changes

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Create (see CI/CD workflow section below) |
| `backend/pyproject.toml` | Verify `pytest-cov` present (added in Phase 0) |

### Jobs
- **backend:** Python 3.13, uv cache, ruff lint+format, mypy, pytest `-m "not slow" --cov=app --cov-fail-under=60`
- **frontend:** Node 22, npm cache, eslint, `tsc --noEmit --project tsconfig.app.json`
- **e2e:** Gated behind `workflow_dispatch` or `schedule` only — requires Ollama, not in PR checks

### Acceptance Criteria
- Push to any branch triggers CI
- PR to `master` blocks merge if backend or frontend job fails
- E2E never runs on PR

---

## Phase 3: Backend Test Coverage

**Goal:** Reach 60% backend coverage with tests that work without Ollama.
**Effort:** 6–8 hours

### Changes

| File | Change |
|------|--------|
| `backend/tests/unit/test_chat_service.py` | New: `create_session`, `get_session_history`, `cleanup_expired_sessions` |
| `backend/tests/unit/test_auth.py` | New: `create_access_token`, `verify_password`, `load_users_from_env`, token decode |
| `backend/tests/unit/test_config.py` | New: `get_available_providers`, settings defaults |
| `backend/tests/integration/test_routes.py` | New: all routes with mocked `ChatService` |
| `backend/tests/conftest.py` | Add `chat_service` fixture, `test_app` fixture with DI overrides |
| `backend/tests/integration/test_chat_service_mocked_llm.py.skip` | Delete — references non-existent `app.domain.chat` architecture, full rewrite needed |

### Acceptance Criteria
- `uv run pytest --cov=app --cov-fail-under=60 -m "not slow"` passes
- No test requires network access or Ollama
- All tests use AAA pattern with descriptive names

**Skills:** `everything-claude-code:tdd`, `everything-claude-code:python-testing`

---

## Phase 4: Frontend Testing and Refactor

**Goal:** Install Vitest, decompose `ChatInterface.tsx` (452 lines), add unit tests.
**Effort:** 6–8 hours

### Changes

| File | Change |
|------|--------|
| `frontend/package.json` | Add devDeps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `@vitest/coverage-v8` |
| `frontend/vitest.config.ts` | New: jsdom environment, coverage config |
| `frontend/src/types/chat.ts` | New: extract `Message`, `ToolCallMetadata`, `ToolResultMetadata`, `ToolExecutionData`, `StreamEvent` |
| `frontend/src/lib/parseSSE.ts` | New: pure function, parse SSE line → typed event |
| `frontend/src/hooks/useSSEStream.ts` | New: SSE reader/decoder logic extracted from `ChatInterface.tsx` |
| `frontend/src/hooks/useChat.ts` | New: message accumulation, session management, error handling |
| `frontend/src/components/ChatInterface.tsx` | Refactor: consume `useChat`, reduce to ~150 lines (presentation only) |
| `frontend/src/lib/__tests__/parseSSE.test.ts` | New: unit tests for SSE parsing |
| `frontend/src/hooks/__tests__/useChat.test.ts` | New: hook tests with mocked fetch |
| `frontend/package.json` scripts | Add `"test": "vitest"`, `"test:coverage": "vitest run --coverage"` |

### Acceptance Criteria
- `npm test` runs Vitest
- `parseSSE` has 100% branch coverage
- `useChat` hook tested with mocked fetch
- `ChatInterface.tsx` under 200 lines
- `npm run lint && npx tsc --noEmit --project tsconfig.app.json` still passes

**Skills:** `everything-claude-code:frontend-patterns`, `chakra-ui` (local)

---

## Phase 5: Security and Operational Hardening

**Goal:** CSP headers, safe CORS, rate limiting, sanitized markdown rendering.
**Effort:** 4–5 hours

### Changes

| File | Change |
|------|--------|
| `backend/app/config.py` | Add `cors_origins: list[str] = ["http://localhost:5173"]` |
| `backend/app/api/main.py` | Replace hardcoded CORS with `settings.cors_origins`; never allow `*` silently |
| `backend/app/middleware/security.py` | New: CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy headers |
| `backend/app/api/main.py` | Register security middleware |
| `backend/pyproject.toml` | Add `slowapi>=0.1.9` |
| `backend/app/middleware/rate_limit.py` | New: slowapi with `X-Forwarded-For` key function; per-user limits |
| `frontend/package.json` | Add `rehype-sanitize` |
| `frontend/src/lib/sanitizeConfig.ts` | New: custom rehype-sanitize config preserving Chakra table elements |
| `frontend/src/components/ChatInterface.tsx` | Add `rehypeSanitize` to all `<ReactMarkdown>` instances |

### Acceptance Criteria
- Response headers include CSP, X-Frame-Options, etc.
- CORS rejects unlisted origins
- Rate limiter returns 429 after threshold; uses `X-Forwarded-For` when present
- Markdown tables still render correctly with sanitization on
- `<script>alert(1)</script>` in LLM output renders as escaped text

**Skills:** `everything-claude-code:security-review`, `fastapi` (local)

---

## Phase 6: Coverage Ratchet to 80%

**Goal:** Raise CI threshold from 60% to 80%.
**Effort:** 4–6 hours

### Changes

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Change `--cov-fail-under=60` → `--cov-fail-under=80` |
| `backend/tests/unit/test_flight_search.py` | Expand: all validation branches in `search_flights` tool |
| `backend/tests/unit/test_models.py` | New: all Pydantic validators (IATA, dates, booking class normalization) |
| `backend/tests/unit/test_middleware.py` | New: CSP headers, rate limit responses |
| `frontend/vitest.config.ts` | Add coverage threshold: `{ branches: 70, lines: 80 }` |

**Skills:** `everything-claude-code:tdd`, `everything-claude-code:python-testing`

---

## Skills Reference

| Phase | Skills |
|-------|--------|
| 0 | `everything-claude-code:python-review` |
| 1 | `fastapi` (local), `everything-claude-code:tdd`, `everything-claude-code:security-review` |
| 2 | N/A |
| 3 | `everything-claude-code:tdd`, `everything-claude-code:python-testing` |
| 4 | `everything-claude-code:frontend-patterns`, `chakra-ui` (local) |
| 5 | `everything-claude-code:security-review`, `fastapi` (local) |
| 6 | `everything-claude-code:tdd`, `everything-claude-code:python-testing` |
| Any (LangChain/SSE docs) | `context7` MCP tool |

---

## Deferred Items

| Item | Reason |
|------|--------|
| Per-session LLM factory (provider switching) | Large blast radius — breaks `ChatService.__init__`, all fixtures, all tests. Defer until multi-provider is real user need. |
| Database persistence | In-memory fine for MVP. Add when session persistence across restarts needed. |
| Docker / docker-compose | Add after CI green + auth stable. Must override `OLLAMA_BASE_URL` (not `localhost` inside container). |
| `openapi-typescript` codegen for TS types | Better long-term than manual `types/chat.ts`, but premature until API stabilizes. |
| Playwright frontend E2E | Add after Phase 4 component refactor stabilizes. |
| `ToolCallCard.tsx` + `ToolResultCard.tsx` deletion | Currently unused (superseded by `ToolExecutionCard`). Delete after Phase 4 dedup confirms orphaned. |

---

## Known Limitations (Accepted)

| Limitation | Mitigation |
|-----------|------------|
| No token revocation (no DB deny-list) | Short JWT expiry (60 min); rotate `jwt_secret` on breach |
| In-memory sessions lost on restart | Acceptable for MVP |
| Rate limiting resets on restart, single-process only | Add Redis backend when scaling |
| E2E tests require Ollama — not in PR CI | Gated to manual/scheduled workflow |
| Auth users from env vars only | Acceptable for internal/demo; add registration later |
| `search_flights._flight_client` monkey-patch remains | Works, contained. Refactor when adding more tools. |
