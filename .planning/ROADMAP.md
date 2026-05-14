# Roadmap: Trip Planner

## Overview

Trip Planner began as a learning/demo of an AI-powered chat agent that calls travel tools live and surfaces structured, sanitized results to a React + Chakra UI v3 frontend. Phases 1-3 and sub-phase 4.1 have already shipped, plus engineering-quality PRs #1-#5. The active milestone is **Phase 4 Provider Flexibility + UI Polish through to a production-ready demo**: complete sub-phases 4.2 → 4.4, integrate a real flight API in Phase 5, and harden the system for production in Phase 6. The product-phase numbering scheme (legacy `ROADMAP.md`) is authoritative; engineering items run as a cross-cutting Quality Workstream that lands inside Phases 4.4 / 5 / 6 alongside product features.

## Milestones

- ✅ **v0 Foundation + Mock Demo** — Phases 1-3, 4.1 (shipped 2025-11-06 → 2026-05-13)
- 🚧 **v1 Production-Ready Demo** — Phases 4.2-6 (in progress)
- 📋 **v2 Persistence, Deployment, Travel Expansion** — see REQUIREMENTS.md v2 section (planned)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 5, 6): Product milestones from the legacy `ROADMAP.md`.
- Decimal phases (4.1, 4.2, 4.3, 4.4): Sub-phases of the Phase 4 milestone (Provider Flexibility + UI Polish).
- Engineering-quality work is folded into product phases as a cross-cutting Quality Workstream — there is no parallel "engineering Phase N" track.

- [x] **Phase 1: Foundation & FastAPI Setup** - Python 3.13 + uv, FastAPI, ruff/mypy/pytest, Vite + React + TS + Chakra UI v3, justfile, JWT auth, CI
- [x] **Phase 2: LangChain Integration & Chat Agent** - LangChain 1.0 `bind_tools()`, Ollama, SSE streaming, session memory, frontend testing infra + hooks decomposition
- [x] **Phase 3: Mock Flight Search Tool** - Pydantic models, abstract client, `@tool` agent, `ToolExecutionCard` + `ThinkingCard`, qwen3:4b reasoning
- [x] **Phase 4.1: LLM Provider UI Config** - `GET /api/providers`, session creation accepts `{provider, model}`, frontend dropdown, localStorage persistence
- [ ] **Phase 4.2: Structured Tool Output** - `search_flights` returns structured JSON; `ToolExecutionCard` renders tables/lists/nested objects
- [ ] **Phase 4.3: Error Handling + StreamEvent Hierarchy** - Discriminated `StreamEvent` union with `ErrorEvent`; UX-grade error feedback, loading states, retry, toasts
- [ ] **Phase 4.4: Provider Abstraction + Validators + Test Hygiene** - `LLMProvider` Protocol + factory, Pydantic business-rule validators, shared test fixtures, orphan component cleanup
- [ ] **Phase 5: Real Flight API** - Replace `MockFlightAPIClient` with a real provider (Amadeus or equivalent) behind the existing ABC; retry, circuit breaker, error mapping; gated integration tests
- [ ] **Phase 6: Production-Readiness Quality Workstream** - Security headers + CORS allowlist + `slowapi` + Chakra-aware `rehype-sanitize`; `structlog` + `RequestLoggingMiddleware`; backend coverage 60→80, frontend `{ branches: 70, lines: 80 }`

## Phase Details

### Phase 1: Foundation & FastAPI Setup
**Goal**: A typed, tested, CI-gated, JWT-authenticated FastAPI + React monorepo skeleton that any future feature can ship on top of.
**Depends on**: Nothing (first phase)
**Requirements**: REQ-bug-fixes-cleanup, REQ-auth-hardening, REQ-ci-cd-pipeline
**Status**: Complete (shipped 2025-11-06 → 2025-11-08; quality PRs #1, #2, #4 landed retroactively)
**Success Criteria** (what must be TRUE):
  1. `just install` followed by `just backend` and `just frontend` brings up both servers cleanly on Python 3.13 / Node 22.
  2. `just check` (ruff lint + format-check + mypy strict + tsc + eslint) passes; CI enforces the same gates with a 60% backend coverage floor.
  3. `POST /token` issues a JWT (HS256, 60-min expiry) using users from `AUTH_USERS`; protected routes reject missing/invalid tokens; `GET /health` is public.
  4. Branch protection on `master` blocks merges that fail Backend (Python 3.13) or Frontend (Node 22) jobs; E2E job is gated to `workflow_dispatch`/`schedule`.
**Plans**: Complete (retroactive — PRs #1, #2, #4)

### Phase 2: LangChain Integration & Chat Agent
**Goal**: A streaming chat agent backed by LangChain 1.0 `bind_tools()` and Ollama, with a React frontend that consumes the SSE stream and renders markdown.
**Depends on**: Phase 1
**Requirements**: REQ-frontend-testing-refactor
**Status**: Complete (shipped 2025-11-08 → 2025-11-10; PR #3 landed retroactively against this surface)
**Success Criteria** (what must be TRUE):
  1. A user holds a multi-turn conversation in the React UI and sees streamed responses arrive token-by-token over SSE.
  2. Sessions persist message history across requests via `ChatService._histories` (no global store).
  3. `ChatInterface.tsx` is decomposed into `lib/parseSSE.ts`, `hooks/useSSEStream.ts`, `hooks/useChat.ts`; the component is under 200 lines.
  4. Vitest + `@testing-library/react` + `@vitest/coverage-v8` are wired up; unit tests cover `parseSSE` and `useChat`.
**Plans**: Complete (retroactive — PR #3)
**UI hint**: yes

### Phase 3: Mock Flight Search Tool
**Goal**: The agent can call a mock flight-search tool, the LLM streams reasoning tokens, and the frontend renders tool execution and thinking cards live.
**Depends on**: Phase 2
**Requirements**: *(none active — Phase 3 deliverables are foundational and shipped before the v1 milestone scope)*
**Status**: Complete (shipped 2025-11-10 → 2025-11-14)
**Success Criteria** (what must be TRUE):
  1. A user asks the agent for flights and watches a `ToolExecutionCard` appear with tool name, args, and result, plus a `ThinkingCard` showing reasoning tokens.
  2. `MockFlightAPIClient` returns realistic data through the `FlightAPIClient` ABC; the client is injected at startup via `search_flights._flight_client`.
  3. SSE event stream emits the four current event types (`content`, `thinking`, `tool_call`, `tool_result`) with `thinking` chunks sourced from `chunk.additional_kwargs["reasoning_content"]`.
  4. qwen3:4b runs in `init_chat_model(reasoning=True)` mode; default `pytest -m "not slow"` passes without Ollama.
**Plans**: Complete
**UI hint**: yes

### Phase 4.1: LLM Provider UI Config
**Goal**: A user can pick provider + model from the UI, the choice is persisted, and a new selection creates a fresh session bound to that config.
**Depends on**: Phase 3
**Requirements**: REQ-llm-provider-ui-config
**Status**: Complete (shipped 2026-05-13)
**Success Criteria** (what must be TRUE):
  1. `GET /api/providers` returns the available providers, each with their models and credential status.
  2. `POST /api/chat/session` accepts `{"provider": "<id>", "model": "<id>"}` and returns `201` with the session metadata `{provider, model, created_at}`.
  3. The frontend renders a provider + model dropdown; the selection survives a page reload via localStorage.
  4. Selecting a different provider creates a new session rather than mutating the active one.
**Plans**: Complete
**UI hint**: yes

### Phase 4.2: Structured Tool Output
**Goal**: Flight search returns structured JSON, and the frontend renders it as readable tables/lists rather than relying on the LLM to format strings.
**Depends on**: Phase 4.1
**Requirements**: REQ-tool-json-output
**Success Criteria** (what must be TRUE):
  1. `search_flights()` returns a structured JSON object with `status`, `query`, `results[]` (each: `flight_number`, `airline`, `route`, `departure`, `arrival`, `duration_hours`, `price_usd`, `stops`), and `count`.
  2. `ToolExecutionCard` renders the structured result as a table for `results[]`, lists for arrays, and labelled sections for nested objects — not as a JSON blob.
  3. Backend tests assert the JSON shape contract; the test suite passes under `pytest -m "not slow"` with no Ollama.
  4. The LLM still narrates results naturally in chat alongside the structured card; the two views are consistent.
**Plans**: TBD
**UI hint**: yes

### Phase 4.3: Error Handling + StreamEvent Hierarchy
**Goal**: A user sees clear, actionable feedback when anything goes wrong (API, session, tool, stream), and the SSE protocol carries errors as a first-class event type.
**Depends on**: Phase 4.2
**Requirements**: REQ-error-handling-feedback, REQ-streamevent-hierarchy
**Success Criteria** (what must be TRUE):
  1. `StreamEvent` is replaced by a discriminated union `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`; backend SSE serialization and frontend `parseSSE` handle each variant.
  2. API, session, and tool errors render as distinct, human-readable messages in the chat UI rather than silent failures or raw stack traces.
  3. `ToolExecutionCard` shows a loading state while a tool call is in flight; failed tool calls expose a retry control that re-issues the call.
  4. Non-blocking errors surface as toast notifications; the streaming UI continues to render subsequent events after a recoverable error.
**Plans**: TBD
**UI hint**: yes

### Phase 4.4: Provider Abstraction + Validators + Test Hygiene
**Goal**: Provider selection runs through a typed Protocol, business rules are enforced at the model boundary, and the test suite shares fixtures instead of duplicating mock data.
**Depends on**: Phase 4.3
**Requirements**: REQ-llm-provider-abstraction, REQ-pydantic-validators, REQ-test-fixture-dedup
**Success Criteria** (what must be TRUE):
  1. `LLMProvider` Protocol exists with `ainvoke`, `astream`, `bind_tools`, `get_provider_name`, `validate_config`; `OllamaProvider` implements it; `LLMProviderFactory` builds providers from session config; `ChatService` accepts a provider via DI rather than a bare `BaseChatModel`.
  2. Submitting an invalid `FlightQuery` (`origin == destination`, `departure_date < today`) or constructing a `Flight` with `arrival_time <= departure_time` is rejected at the model boundary with a clear 422.
  3. `backend/tests/fixtures/flights.py::create_mock_flight()` and `backend/tests/utils/sse.py::parse_sse_events()` exist; existing tests consume them; no test redefines a mock-flight factory inline.
  4. Orphaned `frontend/src/components/ToolCallCard.tsx` and `ToolResultCard.tsx` are deleted (superseded by `ToolExecutionCard`); the frontend builds without dead-import warnings.
**Plans**: TBD
**UI hint**: yes

### Phase 5: Real Flight API
**Goal**: The agent calls a real flight provider (Amadeus or equivalent) through the existing `FlightAPIClient` ABC, with retry, circuit breaker, and clean error mapping; the mock remains the test default.
**Depends on**: Phase 4.4
**Requirements**: REQ-real-flight-api
**Success Criteria** (what must be TRUE):
  1. A user-configurable real provider client implements `FlightAPIClient`, uses `aiohttp` for async I/O, and reuses the existing retry decorator (exponential backoff + circuit breaker) and `APIError` hierarchy (`APITimeoutError`, `APIRateLimitError`, `APIServerError`, `APIClientError`, `FlightSearchError`).
  2. With real credentials configured, `search_flights` returns live results in the same structured JSON contract from Phase 4.2; without credentials, the system falls back to the mock client.
  3. Real-API integration tests exist and are gated to `workflow_dispatch` / `schedule`; PR CI does not require API keys.
  4. `pytest -m "not slow"` continues to pass with the mock client as the DI default; documentation describes credential setup for local and CI use.
**Plans**: TBD

### Phase 6: Production-Readiness Quality Workstream
**Goal**: The demo is production-ready: hardened HTTP layer, structured logs, CORS allowlist, rate limiting, Chakra-aware markdown sanitization, and an 80% backend / 70-branch-80-line frontend coverage gate enforced in CI.
**Depends on**: Phase 5
**Requirements**: REQ-security-hardening, REQ-structured-logging, REQ-backend-test-coverage-60, REQ-coverage-ratchet-80
**Success Criteria** (what must be TRUE):
  1. Every response carries CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and Permissions-Policy headers; CORS uses `settings.cors_origins` (no wildcard); `slowapi` returns 429 over threshold using an `X-Forwarded-For`-aware key.
  2. All `<ReactMarkdown>` instances run through `rehype-sanitize` with the custom Chakra-aware `sanitizeConfig.ts`: `<script>alert(1)</script>` in LLM output renders as escaped text and Chakra-rendered flight tables continue to render correctly.
  3. `structlog` JSON logging is configured at startup; `RequestLoggingMiddleware` issues a `request_id` per request; `ChatService` logs tool calls, streaming durations, and errors with `request_id` and `session_id`.
  4. CI enforces `pytest --cov=app --cov-fail-under=80 -m "not slow"` and frontend `coverage: { branches: 70, lines: 80 }`; new tests cover validation branches, model validators, and middleware.
  5. A security review of the production-mode demo finds zero CRITICAL findings; a user can switch LLM providers from the UI and receive structured, sanitized flight results from the real API end-to-end.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4.1 → 4.2 → 4.3 → 4.4 → 5 → 6.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation & FastAPI Setup | v0 | retro / retro | Complete | 2025-11-08 |
| 2. LangChain Integration & Chat Agent | v0 | retro / retro | Complete | 2025-11-10 |
| 3. Mock Flight Search Tool | v0 | retro / retro | Complete | 2025-11-14 |
| 4.1. LLM Provider UI Config | v0 | retro / retro | Complete | 2026-05-13 |
| 4.2. Structured Tool Output | v1 | 0 / TBD | Not started | - |
| 4.3. Error Handling + StreamEvent Hierarchy | v1 | 0 / TBD | Not started | - |
| 4.4. Provider Abstraction + Validators + Test Hygiene | v1 | 0 / TBD | Not started | - |
| 5. Real Flight API | v1 | 0 / TBD | Not started | - |
| 6. Production-Readiness Quality Workstream | v1 | 0 / TBD | Not started | - |

## Coverage

All 16 v1 requirements (5 validated + 11 active) map to exactly one phase. See `REQUIREMENTS.md` Traceability table for the full ID-to-phase mapping. No orphans; no duplicates.

---
*Roadmap created: 2026-05-14 by `gsd-roadmapper` (resume-from-partial). Aligned with `PROJECT.md` and `REQUIREMENTS.md` already on disk; product-phase numbering scheme from legacy `/Users/axel/code/trip_planner/ROADMAP.md` is authoritative per user direction.*
