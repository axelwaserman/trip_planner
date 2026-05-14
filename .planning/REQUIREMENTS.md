# Requirements: Trip Planner

**Defined:** 2026-05-14
**Core Value:** A user can hold a natural conversation with an AI agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully — across multiple LLM providers selected from the UI.

## v1 Requirements

Requirements for the active milestone: **Phase 4 Provider Flexibility + UI Polish through to a production-ready demo (Phases 4.2 → 6)**. The product-phase numbering scheme from the legacy `ROADMAP.md` is authoritative; engineering-quality items are folded into product phases as a cross-cutting Quality Workstream rather than competing phase numbers.

Several requirements have already shipped on `master` (PRs #1-#5 and Phase 4.1) — they are listed here as **Validated** for traceability and explicitly marked `Complete (shipped)` in the traceability table so downstream tools do not re-execute them.

### Validated (shipped pre-roadmap)

- ✓ **REQ-bug-fixes-cleanup** — Pre-Phase-4 bug fixes: `_metadata` deletion in `delete_session`, `get_session_history` raises `ValueError`, e2e import paths fixed, `langgraph` removed from deps, `pytest-cov` added (PR #1)
- ✓ **REQ-auth-hardening** — JWT auth via `pyjwt` + `pwdlib[argon2]`; `POST /token`; protected routes via `Depends(get_current_active_user)`; in-memory user store seeded from `AUTH_USERS` env var; `GET /health` public (PR #4)
- ✓ **REQ-ci-cd-pipeline** — GitHub Actions CI: backend (ruff lint+format, mypy, pytest `-m "not slow" --cov=app --cov-fail-under=60`); frontend (eslint, `tsc --noEmit`); E2E gated to `workflow_dispatch`/`schedule`; branch protection on master; `concurrency` cancel-in-progress (PR #2)
- ✓ **REQ-frontend-testing-refactor** — Vitest + `@testing-library/react` + `jsdom` + `@vitest/coverage-v8`; `ChatInterface.tsx` decomposed into `lib/parseSSE.ts`, `hooks/useSSEStream.ts`, `hooks/useChat.ts`; under 200 lines; unit tests for `parseSSE` and `useChat` (PR #3 — hooks-shape variant; reducer variant superseded)
- ✓ **REQ-llm-provider-ui-config** — `GET /api/providers` returns providers/models/credential status; `POST /api/chat/session` accepts `{provider, model}`; frontend dropdown for provider + model selection; localStorage persistence; selecting a new provider creates a new session (Phase 4.1)

### Active

#### Phase 4.2 — Structured Tool Output

- [ ] **REQ-tool-json-output**: `search_flights()` LangChain tool returns a structured JSON object with `status`, `query`, `results[]` (each item: `flight_number`, `airline`, `route`, `departure`, `arrival`, `duration_hours`, `price_usd`, `stops`), and `count`; the LLM is given freedom to format naturally; `ToolExecutionCard` renders structured data (tables, lists, nested objects); tests validate JSON shape.

#### Phase 4.3 — Error Handling, Feedback, and Event Hierarchy

- [ ] **REQ-error-handling-feedback**: Frontend renders distinct, actionable error messages for API errors, session errors, and tool errors. `ToolExecutionCard` shows a loading state during tool execution. Failed tool calls offer a retry control. Toast notifications surface non-blocking errors. Errors do not silently break the streaming UI.
- [ ] **REQ-streamevent-hierarchy**: Replace the monolithic `StreamEvent` model with a discriminated union — `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`. Update SSE serialization on the backend and `parseSSE` on the frontend. Each event type carries only its own fields. The new `ErrorEvent` is the transport for REQ-error-handling-feedback's tool-error and stream-error paths.

#### Phase 4.4 — Provider Abstraction + Validators + Test Hygiene

- [ ] **REQ-llm-provider-abstraction**: Formalize an `LLMProvider` Protocol with `ainvoke`, `astream`, `bind_tools`, `get_provider_name`, `validate_config`. Implement `OllamaProvider` (and stubs for OpenAI/Anthropic if their API keys are present). Add `LLMProviderFactory` that builds a provider from session-scoped config. `ChatService` accepts a provider via DI rather than the bare `BaseChatModel`. Provider validation checks for required config (e.g. API keys) and surfaces clear errors at session creation.
- [ ] **REQ-pydantic-validators**: Add field/model validators enforcing business rules — `Flight.arrival_time > Flight.departure_time`; `FlightQuery.departure_date >= today`; `FlightQuery.origin != FlightQuery.destination`. Invalid data rejected at the model boundary with a clear 422 response.
- [ ] **REQ-test-fixture-dedup**: Extract `create_mock_flight()` into `backend/tests/fixtures/flights.py` and `parse_sse_events()` into `backend/tests/utils/sse.py`. Refactor existing tests to consume them. Delete orphaned `frontend/src/components/ToolCallCard.tsx` and `ToolResultCard.tsx` (superseded by `ToolExecutionCard`).

#### Phase 5 — Real Flight API

- [ ] **REQ-real-flight-api**: Replace `MockFlightAPIClient` (the default in dev/test) with a real flight provider client (Amadeus or equivalent) behind the existing `FlightAPIClient` ABC. Real client uses `aiohttp`, the existing retry decorator (exponential backoff + circuit breaker), and the `APIError` hierarchy (`APITimeoutError`, `APIRateLimitError`, `APIServerError`, `APIClientError`, `FlightSearchError`). Mock client remains the default in tests via DI override. Real-API integration tests are gated to `workflow_dispatch` / `schedule` (no API key required for PR CI). Documentation describes credential setup.

#### Phase 6 — Production-Readiness Quality Workstream

- [ ] **REQ-security-hardening**: Security middleware emits CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy on every response. CORS comes from `settings.cors_origins` (default `["http://localhost:5173"]`); wildcard `*` is rejected. `slowapi`-based rate limiting with an `X-Forwarded-For`-aware key function returns 429 over threshold. All `<ReactMarkdown>` instances use `rehype-sanitize` with the custom Chakra-aware `sanitizeConfig.ts` that preserves table elements; `<script>alert(1)</script>` in LLM output renders as escaped text; flight-result tables still render correctly.
- [ ] **REQ-structured-logging**: `structlog`-based JSON logging configured at startup. `RequestLoggingMiddleware` generates a `request_id` per request and attaches it to the log context. `ChatService` logs tool calls, streaming durations, and errors with `request_id` and `session_id`. Logs are JSON-formatted in production.
- [ ] **REQ-backend-test-coverage-60**: New no-network / no-Ollama tests bring backend coverage to ≥ 60% as measured by `pytest --cov=app --cov-fail-under=60 -m "not slow"`. Adds `test_chat_service.py`, `test_auth.py`, `test_config.py`, `test_routes.py`. Deletes `test_chat_service_mocked_llm.py.skip`. AAA pattern with descriptive names.
- [ ] **REQ-coverage-ratchet-80**: CI threshold raised to `--cov-fail-under=80`. New tests: `test_flight_search.py` (validation branches), `test_models.py` (Pydantic validators), `test_middleware.py` (CSP, rate limit). Frontend `vitest.config.ts` enforces `coverage: { branches: 70, lines: 80 }`.

## v2 Requirements

Acknowledged but deferred. Not in the active roadmap; tracked here for visibility.

### Persistence & Deployment

- **PERSIST-01**: PostgreSQL-backed session/message persistence (sessions survive restart)
- **DEPLOY-01**: Docker / docker-compose packaging with `OLLAMA_BASE_URL` override
- **DEPLOY-02**: First production deployment target chosen and provisioned

### Auth & Security (post-MVP)

- **AUTH2-01**: JWT token revocation / deny-list (DB-backed)
- **AUTH2-02**: User registration endpoint
- **SEC2-01**: Redis-backed rate limiter (horizontally scalable)

### Tooling

- **TOOL-01**: `openapi-typescript` codegen for frontend types (replace hand-written `types/chat.ts`)
- **TOOL-02**: Playwright frontend E2E suite

### Travel Features

- **TRAVEL-01**: Hotel search tool
- **TRAVEL-02**: Restaurant search tool
- **TRAVEL-03**: Weather tool
- **TRAVEL-04**: Multi-city / multi-leg trip planning

### Architecture Pivots

- **ARCH-01**: DSPy integration
- **ARCH-02**: GraphQL API migration

## Out of Scope

Explicitly excluded from v1 with reasoning. Listed here so they are not silently re-added.

| Feature | Reason |
|---------|--------|
| Session-management refactor (introduce `SessionStore` ABC, replace global `_global_chat_store`) | **Premise was wrong.** `ChatService._histories` already provides per-instance session storage; no global store ever existed. Confirmed by `NOW.md` 2025-11-14 and `CLAUDE.md`. |
| DI lifespan refactor (replace `@lru_cache` singletons with `app.state`) | **Premise was wrong.** Singletons already live in `app.state` via `lifespan()`. No `@lru_cache` factories exist. Confirmed by `CLAUDE.md`. |
| Default-config `rehype-sanitize` drop-in (pre-phase-4-refactor Task 10) | Superseded by the Chakra-aware custom `sanitizeConfig.ts` (REQ-security-hardening). Default config strips Chakra table elements and silently regresses flight-result rendering. |
| Reducer-based `ChatInterface` decomposition (pre-phase-4-refactor Task 5) | Superseded by the hooks-shape decomposition shipped in PR #3. |
| JWT token revocation / deny-list | Mitigated by 60-min token expiry and `jwt_secret` rotation on breach. Deferred to v2. |
| Database persistence | In-memory sessions sufficient for MVP demo; deferred to v2. |
| Docker / docker-compose | Deferred until CI green + auth stable + first deployment target chosen; see v2. |
| `openapi-typescript` codegen | Premature until API contract stabilizes; deferred to v2. |
| Playwright frontend E2E | Defer until after Phase 4 component refactor stabilizes; deferred to v2. |
| User registration endpoint | Internal/demo project; users seeded from `AUTH_USERS` env var. Deferred to v2. |
| Redis-backed rate limiter | Single-process in-memory limiter acceptable for demo; defer to v2. |
| Additional travel tools (hotels, restaurants, weather) | v1 covers flights only; deferred to v2. |
| Multi-city / multi-leg trip planning | v1 covers single origin/destination/date; deferred to v2. |
| DSPy / GraphQL migration | Architectural pivots, not in v1 scope; deferred to v2. |

## Traceability

Each v1 requirement maps to exactly one phase. **Validated** requirements are listed for completeness with status `Complete (shipped)` so downstream tools do not re-execute them.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-bug-fixes-cleanup | Phase 1 (foundation, retroactive) | Complete (shipped, PR #1) |
| REQ-auth-hardening | Phase 1 (foundation, retroactive) | Complete (shipped, PR #4) |
| REQ-ci-cd-pipeline | Phase 1 (foundation, retroactive) | Complete (shipped, PR #2) |
| REQ-frontend-testing-refactor | Phase 2 (LangChain integration, retroactive) | Complete (shipped, PR #3) |
| REQ-llm-provider-ui-config | Phase 4.1 | Complete (shipped) |
| REQ-tool-json-output | Phase 4.2 | Pending |
| REQ-error-handling-feedback | Phase 4.3 | Pending |
| REQ-streamevent-hierarchy | Phase 4.3 | Pending |
| REQ-llm-provider-abstraction | Phase 4.4 | Pending |
| REQ-pydantic-validators | Phase 4.4 | Pending |
| REQ-test-fixture-dedup | Phase 4.4 | Pending |
| REQ-real-flight-api | Phase 5 | Pending |
| REQ-security-hardening | Phase 6 | Pending |
| REQ-structured-logging | Phase 6 | Pending |
| REQ-backend-test-coverage-60 | Phase 6 | Pending |
| REQ-coverage-ratchet-80 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 16 total (5 validated + 11 active)
- Mapped to phases: 16
- Unmapped: 0 ✓

**Note on retroactive mapping for shipped requirements:** PRs #1, #2, #4 landed alongside Phase 1 product work as the foundational quality gates the project was missing; PR #3 landed alongside Phase 2-era frontend work. The phase column for shipped items records this retroactive mapping. The roadmap proper begins at Phase 4.2 — no work is re-scheduled for already-shipped requirements.

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-05-14 after `gsd-roadmapper` synthesis from `.planning/intel/SYNTHESIS.md` (mode: new-project-from-ingest).*
