# Roadmap: Trip Planner

## Overview

Trip Planner is an AI-powered chat agent that calls travel tools live and surfaces structured, sanitized results to a React + Chakra UI v3 frontend. Phases 1-3 shipped end-to-end; Phase 4.1 + auth + CI shipped *partially* (UI without working wiring; backend without login UI; CI with the wrong trigger schedule), so the app is **not currently usable in a browser**. v1 begins by unbreaking the app, then resets CI, then mocks Ollama out of default tests, then makes the LLM provider abstraction real (cloud + dynamic Ollama), then redesigns the tool JSON contract to map onto real travel APIs, then layers errors / discriminated `StreamEvent` / Pydantic validators, then re-platforms onto Postgres + Redis + docker-compose, then migrates from LangChain to PydanticAI, then ships the real flight API, then hardens the HTTP layer (no rate limiting in v1).

## Milestones

- ✅ **v0 Foundation + Mock Demo** — Phases 1-3 (shipped 2025-11-06 → 2025-11-14); 4.1 partial (shipped 2026-05-13, UI without working wiring)
- 🚧 **v1 Working Demo** — Phases 4.2-4.8 (in progress; unbreak → CI reset → mock chat → real provider abstraction → vendor-neutral tool JSON → errors + StreamEvent → validators)
- 🚧 **v1.5 Re-platform** — Phase 5 Postgres + Redis + docker-compose → Phase 6 PydanticAI migration
- 🚧 **v2 Production** — Phase 7 Real Flight API (`pyreqwest` + Amadeus) → Phase 8 Hardening (security headers + structlog + coverage; **no rate limiting**)
- 📋 **post-v1** — see REQUIREMENTS.md v2 section

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 5, 6, 7, 8): Product milestones.
- Decimal phases (4.1 → 4.8): Sub-phases of the Phase 4 working-demo milestone.
- Engineering-quality work is folded into the renumbered phase tree — there is no parallel "engineering Phase N" track.

- [x] **Phase 1: Foundation & FastAPI Setup** — Python 3.13 + uv, FastAPI, ruff/mypy/pytest, Vite + React + TS + Chakra UI v3, justfile, JWT backend
- [x] **Phase 2: LangChain Integration & Chat Agent** — LangChain 1.0 `bind_tools()`, Ollama, SSE streaming, session memory, frontend testing infra + hooks decomposition
- [x] **Phase 3: Mock Flight Search Tool** — Pydantic models, abstract client, `@tool` agent, `ToolExecutionCard` + `ThinkingCard`, qwen3:4b reasoning
- [~] **Phase 4.1: LLM Provider UI Config (partial)** — `GET /api/providers`, session creation accepts `{provider, model}`, frontend dropdown, localStorage persistence; **wiring broken — model selector does not produce a working session**. Reopened in 4.2.
- [ ] **Phase 4.2: Unbreak the App** — React `/login` route + protected routing (REQ-login-page); fix model selector wiring (REQ-llm-provider-ui-fix). Quick-and-dirty: keep `AUTH_USERS` env-seed; PG-seeded users land in Phase 5.
- [ ] **Phase 4.3: CI Reset + Lint/DI Migration** — drop the nightly schedule; lint + unit + integration on every PR push, required for merge; E2E retained only for auth flow + real travel API, gated on credentials. Also: ruff line length 100 → 120 across the codebase, and FastAPI routes migrated from bare `Depends()` to `Annotated[T, Depends(...)]`.
- [ ] **Phase 4.4: Mock Chat in Tests** — `MockLLMStream` fixture replaces Ollama-bound chat tests; `slow` marker removed; doc unit/integration/e2e roles by purpose.
- [ ] **Phase 4.5: LLM Provider Abstraction (real cloud + dynamic Ollama)** — `LLMProvider` Protocol + factory; dynamic Ollama model discovery from host; real OpenAI + Anthropic providers via API key (env or session payload); per-session injection.
- [ ] **Phase 4.6: Vendor-Neutral Tool JSON** — `search_flights()` JSON shape designed against Amadeus / Skyscanner / Google Flights field maps; `ToolExecutionCard` renders tables/lists/nested objects.
- [ ] **Phase 4.7: Error Handling + StreamEvent Hierarchy** — discriminated `StreamEvent` union with `ErrorEvent`; UX-grade error feedback, loading states, retry, toasts.
- [ ] **Phase 4.8: Validators + Test Hygiene + Orphan Cleanup** — additive Pydantic business-rule validators; shared test fixtures (`create_mock_flight()`, `parse_sse_events()`); delete orphan `ToolCallCard` / `ToolResultCard`.
- [ ] **Phase 5: Postgres + Redis + docker-compose** — `psycopg` async + `sqlmodel` ORM; `User`/`Session`/`Message` tables; named volumes; `OLLAMA_BASE_URL` overridable; CORS resolved by compose network; `AUTH_USERS` env-seed retired.
- [ ] **Phase 6: PydanticAI Migration** — port `ChatService` from LangChain `bind_tools()` to PydanticAI `Agent`; preserve SSE event contract; remove `langchain*` deps; ADR-001 → Superseded.
- [ ] **Phase 7: Real Flight API** — Amadeus client behind existing `FlightAPIClient` ABC; **outbound HTTP via `pyreqwest`**; reuse retry + circuit breaker + `APIError` hierarchy; gated integration tests.
- [ ] **Phase 8: Production Hardening (slim)** — CSP / X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy headers; Chakra-aware `rehype-sanitize`; `structlog` + `RequestLoggingMiddleware`; backend coverage 60 → 80; frontend `{ branches: 70, lines: 80 }`. **No rate limiting** (ADR-009).

## Phase Details

### Phase 1: Foundation & FastAPI Setup
**Goal**: A typed, tested, CI-gated, JWT-authenticated FastAPI + React monorepo skeleton that any future feature can ship on top of.
**Depends on**: Nothing (first phase)
**Requirements**: REQ-bug-fixes-cleanup, REQ-auth-backend (partial — login UI deferred to Phase 4.2), REQ-ci-cd-pipeline (partial — schedule reset deferred to Phase 4.3), REQ-mypy-eslint-cleanup
**Status**: Partially complete (shipped 2025-11-06 → 2025-11-08; quality PRs #1, #2, #4, #5 landed retroactively). Frontend login route + correct CI triggers reopened as REQ-login-page (4.2) and REQ-ci-reset (4.3).
**Success Criteria** (what must be TRUE):
  1. `just install` followed by `just backend` and `just frontend` brings up both servers cleanly on Python 3.13 / Node 22.
  2. `just check` (ruff lint + format-check + mypy strict + tsc + eslint) passes; CI enforces the same gates with a 60% backend coverage floor.
  3. `POST /token` issues a JWT (HS256, 60-min expiry) using users from `AUTH_USERS`; protected routes reject missing/invalid tokens; `GET /health` is public. **Frontend login UI required for end-to-end usability — see Phase 4.2.**
  4. Branch protection on `master` blocks merges that fail Backend (Python 3.13) or Frontend (Node 22) jobs. **CI trigger schedule reset — see Phase 4.3.**
**Plans**: Complete (retroactive — PRs #1, #2, #4, #5)

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

### Phase 4.1: LLM Provider UI Config (partial)
**Goal**: A user can pick provider + model from the UI, the choice is persisted, and a new selection creates a fresh session bound to that config.
**Depends on**: Phase 3
**Requirements**: REQ-llm-provider-ui-config
**Status**: **Partial (shipped 2026-05-13)** — UI ships and persists selection, but the in-browser model selector does **not** produce a working session (wiring broken). Reopened as REQ-llm-provider-ui-fix in Phase 4.2.
**Success Criteria** (what must be TRUE):
  1. `GET /api/providers` returns the available providers, each with their models and credential status. ✓
  2. `POST /api/chat/session` accepts `{"provider": "<id>", "model": "<id>"}` and returns `201` with the session metadata `{session_id, provider, model}`. ✓
  3. The frontend renders a provider + model dropdown; the selection survives a page reload via localStorage. ✓
  4. Selecting a different provider creates a new session rather than mutating the active one. **⚠️ broken — selection does not produce a working session in the browser.**
**Plans**: Partial — REQ-llm-provider-ui-fix (4.2) closes the gap.
**UI hint**: yes

### Phase 4.2: Unbreak the App
**Goal**: A fresh user can open the app in a browser, log in, pick a provider/model, and complete one chat turn end-to-end.
**Depends on**: Phase 4.1 (partial)
**Requirements**: REQ-login-page, REQ-llm-provider-ui-fix
**Success Criteria** (what must be TRUE):
  1. A React `/login` route renders a Chakra UI form; submitting valid credentials calls `POST /token`, stores the JWT, and redirects to the chat. Invalid credentials surface a clear error.
  2. A protected-route wrapper redirects unauthenticated users to `/login`. The chat header shows the logged-in user; logout clears the token.
  3. With Ollama running and at least one local model present, picking a provider+model in the dropdown reliably creates a session and the next chat turn uses it.
  4. Provider misconfiguration (Ollama unreachable, cloud API key missing) renders a deterministic, human-readable error in the UI rather than a silent broken state.
  5. `AUTH_USERS=user1:pass1,...` remains the user source — no Postgres yet (deferred to Phase 5).
**Plans**: 6 plans across 4 waves
Plans:
- [x] 04.2-01-PLAN.md — Wave 0: Create 8 failing test stubs (4 backend, 4 frontend)
- [x] 04.2-02-PLAN.md — Wave 1: Rename auth router to /api/auth + create provider_probe service
- [x] 04.2-03-PLAN.md — Wave 1: Frontend auth lib (auth.ts, providerErrors.ts), theme, BrowserRouter, fonts
- [x] 04.2-04-PLAN.md — Wave 2: Wire probe_provider() into POST /api/chat/session
- [x] 04.2-05-PLAN.md — Wave 2: Login page + routing (RequireAuth, LoginForm, UserMenu, App.tsx)
- [ ] 04.2-06-PLAN.md — Wave 3: SelectorErrorBanner + useChat/ProviderSelector rewiring + manual UAT
**UI hint**: yes

### Phase 4.3: CI Reset + Lint/DI Migration
**Goal**: CI runs the right checks at the right times — every PR push runs lint + unit + integration; the nightly schedule is gone; E2E exists only for auth flow + real travel APIs. Lint and DI conventions are also migrated forward in this phase so subsequent phases inherit the modern surface.
**Depends on**: Phase 4.2
**Requirements**: REQ-ci-reset, REQ-lint-line-length-120, REQ-annotated-depends
**Success Criteria** (what must be TRUE):
  1. `.github/workflows/ci.yml` triggers on `pull_request` against `master` and `push` to any branch with an open PR; **no `schedule:` block**.
  2. `lint` + `unit` + `integration` jobs are required for merge by branch protection on `master`.
  3. The `E2E` job is retained but runs only when secrets relevant to auth flow + real travel API are present; it never invokes Ollama.
  4. `concurrency: { group: <workflow>-<ref>, cancel-in-progress: true }` is set so stale runs are cancelled when a new push lands.
  5. `pyproject.toml` `[tool.ruff] line-length = 120`; `ruff format` applied across the codebase; `ruff check` and `ruff format --check` continue to pass.
  6. All FastAPI route dependencies use `Annotated[T, Depends(...)]`; mypy strict still passes; behaviour unchanged.

### Phase 4.4: Mock Chat in Tests
**Goal**: The default test suite is fast and offline — no chat test calls a real Ollama instance.
**Depends on**: Phase 4.3
**Requirements**: REQ-mock-chat-tests
**Success Criteria** (what must be TRUE):
  1. `backend/tests/fixtures/llm.py` exports a `MockLLMStream` fixture producing deterministic streams of `content` / `thinking` / `tool_call` / `tool_result` chunks.
  2. All chat tests in `unit/` and `integration/` consume the mock; no chat test in the default suite calls a real Ollama instance.
  3. The `slow` pytest marker is removed (`pyproject.toml` `addopts` updated). Default `pytest` is fast and offline.
  4. README / `CLAUDE.md` describe what unit / integration / e2e tests *contain* by purpose, not just by directory.

### Phase 4.5: LLM Provider Abstraction (real cloud + dynamic Ollama)
**Goal**: The provider layer supports a real cloud LLM via API key and a dynamically-discovered local Ollama model, both selectable per session.
**Depends on**: Phase 4.4
**Requirements**: REQ-llm-provider-abstraction
**Rework risk**: The Protocol surface (`ainvoke`, `astream`, `bind_tools`) mirrors LangChain's `BaseChatModel`; Phase 6's PydanticAI migration is `Agent`-shaped and will retire `bind_tools` from the Protocol. Either accept the rework or revisit whether to swap Phase 6 forward of Phase 5.
**Success Criteria** (what must be TRUE):
  1. `LLMProvider` Protocol exists with `ainvoke`, `astream`, `bind_tools`, `get_provider_name`, `validate_config`.
  2. `OllamaProvider` discovers models dynamically via Ollama's `GET /api/tags` against `OLLAMA_BASE_URL`; no model list is hard-coded.
  3. `OpenAIProvider` and `AnthropicProvider` are real implementations that accept API keys from env vars or session creation payload — not stubs.
  4. `LLMProviderFactory` builds a provider from session-scoped config; `ChatService` accepts a provider via DI rather than a bare `BaseChatModel`.
  5. `validate_config` surfaces missing API keys as clear 400 errors at session creation; the UI displays the error.
  6. Happy-path acceptance test exists for each real cloud provider, gated on the corresponding API key being present in the test environment (skipped in default PR CI).
**UI hint**: yes

### Phase 4.6: Vendor-Neutral Tool JSON
**Goal**: `search_flights()` returns a JSON shape designed to map cleanly onto Amadeus / Skyscanner / Google Flights responses, ready to back the real Phase 7 client without rework.
**Depends on**: Phase 4.5
**Requirements**: REQ-tool-json-output
**Acceptance fixture sources** (locked at planning time, override in the phase plan if changed):
  - Amadeus: a `FlightOffer` payload from the `developers.amadeus.com/self-service/category/flights` Flight Offers Search public sample.
  - Skyscanner: an `Itinerary` from the Skyscanner Rapid (`partners.skyscanner.net`) public reference docs sample response.
  - Google Flights: a search-response sample from a public Postman / community collection (Google Flights has no public REST API; if no representative sample exists, drop the third fixture and document the omission).
**Schedule risk**: locking the schema before the first real Amadeus call (Phase 7) may surface missing fields. Treat the schema as additively extendable — Phase 7 may append fields without breaking the contract.
**Success Criteria** (what must be TRUE):
  1. `search_flights()` returns `{status, query, results[], count}` where each result has IATA + city + (optional) terminal endpoints, ISO-8601 timestamps with timezone, multi-leg journeys in `segments[]`, price as `{amount, currency}`, and carrier as IATA + display name.
  2. The fixtures above (or their documented substitutes) normalize into our shape without lossy field collapses, asserted by tests in `backend/tests/unit/test_tool_json_normalization.py` (or equivalent).
  3. `ToolExecutionCard` renders the structured result as a table for `results[]`, lists for arrays, and labelled sections for nested objects — never a raw JSON blob.
  4. The LLM still narrates results naturally in chat alongside the structured card; the two views remain consistent.
**Plans**: TBD
**UI hint**: yes

### Phase 4.7: Error Handling + StreamEvent Hierarchy
**Goal**: A user sees clear, actionable feedback when anything goes wrong (API, session, tool, stream), and the SSE protocol carries errors as a first-class event type.
**Depends on**: Phase 4.6
**Requirements**: REQ-error-handling-feedback, REQ-streamevent-hierarchy
**Success Criteria** (what must be TRUE):
  1. `StreamEvent` is replaced by a discriminated union `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`; backend SSE serialization and frontend `parseSSE` handle each variant.
  2. API, session, and tool errors render as distinct, human-readable messages in the chat UI rather than silent failures or raw stack traces.
  3. `ToolExecutionCard` shows a loading state while a tool call is in flight; failed tool calls expose a retry control that re-issues the call.
  4. Non-blocking errors surface as toast notifications; the streaming UI continues to render subsequent events after a recoverable error.
**Plans**: TBD
**UI hint**: yes

### Phase 4.8: Validators + Test Hygiene + Orphan Cleanup
**Goal**: Business rules are enforced at the model boundary, the test suite shares fixtures, and dead components are gone.
**Depends on**: Phase 4.7
**Requirements**: REQ-pydantic-validators, REQ-test-fixture-dedup
**Success Criteria** (what must be TRUE):
  1. Submitting an invalid `FlightQuery` (`origin == destination`, `departure_date < today`) or constructing a `Flight` with `arrival <= departure` is rejected at the model boundary with a clear 422. The existing `validate_dates` validator is preserved (additive, not replacement).
  2. `backend/tests/fixtures/flights.py::create_mock_flight()` and `backend/tests/utils/sse.py::parse_sse_events()` exist; existing tests consume them; no test redefines a mock-flight factory inline.
  3. Orphaned `frontend/src/components/ToolCallCard.tsx` and `ToolResultCard.tsx` are deleted (superseded by `ToolExecutionCard`); the frontend builds without dead-import warnings.
**Plans**: TBD

### Phase 5: Postgres + Redis + docker-compose
**Goal**: A single `docker compose up` brings up backend + frontend + Postgres + Redis with named volumes; in-memory session/user state is replaced by PG-backed storage.
**Depends on**: Phase 4.8
**Requirements**: REQ-postgres-redis-compose
**Pre-phase spike** (do this in the discuss phase, not the plan phase): verify `postgresql+psycopg://` async URI works with SQLModel async session out of the box on SQLAlchemy ≥ 2.0. SQLModel historically targeted `asyncpg`; if `psycopg` async needs custom adapter glue, surface that before locking the model layer.
**Rework risk**: `Message` SQLModel built around LangChain's `BaseChatMessageHistory` shape will need a column/shape revision when Phase 6 swaps in PydanticAI's `ModelMessage` history. Either keep the table generic (JSON `payload` column with a discriminator) or accept the Phase 6 migration cost.
**User-data migration**: existing JWTs issued under the Phase 4.2 `AUTH_USERS` env-seed are invalidated at Phase 5 boot (rotate `jwt_secret`); the bootstrap script re-seeds the same usernames into PG with the same passwords (read once from the env, hashed via `pwdlib`, then env unset). Define this concretely in the Phase 5 plan.
**Success Criteria** (what must be TRUE):
  1. `docker-compose.yml` defines services for `backend`, `frontend`, `postgres`, `redis`, with named volumes for PG data and Redis snapshot. `docker compose up` brings the full stack up reproducibly. Restarting compose preserves data via the named volumes (acceptance test: write a row, `docker compose down`, `docker compose up`, read the row back).
  2. Backend uses `psycopg` async driver + `sqlmodel` for `User`, `Session`, and `Message` models. Migrations (alembic or sqlmodel-native) bring up a fresh DB from empty.
  3. `ChatService` history is Postgres-backed; users move from `AUTH_USERS` env-seed to a PG `users` table seeded by an idempotent bootstrap script — the `AUTH_USERS` env-var workaround is retired.
  4. `OLLAMA_BASE_URL` defaults to `host.docker.internal:11434` inside compose; the host's local Ollama remains reachable.
  5. CORS hard-coding in `api/main.py` is removed — the compose network collapses backend + frontend onto a single origin via the proxy. Any non-compose deployment defers CORS to Phase 8's `settings.cors_origins`.
  6. `just install` and `just backend` document the compose path; the legacy "run uv + npm directly" path remains supported for fast inner-loop iteration.

### Phase 6: PydanticAI Migration
**Goal**: The chat agent runs on PydanticAI rather than LangChain — lighter, easier to test — preserving the **frontend-facing** SSE event contract from Phase 4.7. The internal extraction of thinking + tool_call chunks is rewritten against PydanticAI's stream surface.
**Depends on**: Phase 5
**Requirements**: REQ-pydantic-ai-migration
**Backward-compat scope**: the discriminated `StreamEvent` union (`ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`) over the wire is preserved unchanged. Inside `ChatService`, the LangChain-specific `chunk.additional_kwargs["reasoning_content"]` extraction is replaced by the equivalent PydanticAI accessor — this is **not** a verbatim port. `LLMProvider` Protocol from Phase 4.5 has its `bind_tools` member retired; `OllamaProvider`/`OpenAIProvider`/`AnthropicProvider` are reshaped around PydanticAI `Model` + `Agent`. The Phase 5 `Message` SQLModel is migrated forward (or retro-fitted) to PydanticAI's `ModelMessage` shape.
**Success Criteria** (what must be TRUE):
  1. `ChatService` orchestrates a PydanticAI `Agent` per session; tool registration moves from LangChain `@tool` to PydanticAI's tool API.
  2. The discriminated `StreamEvent` union over the SSE wire is preserved — frontend requires no changes; backend extraction is rewritten.
  3. `langchain`, `langchain-core`, `langchain-ollama` are removed from `pyproject.toml`; `pydantic-ai` is added; `uv lock` reflects the swap.
  4. The `MockLLMStream` fixture (Phase 4.4) is updated to drive the PydanticAI agent surface; default `pytest` remains fast and offline.
  5. The Phase 5 `Message` table either fits PydanticAI's `ModelMessage` shape via a migration or has been kept generic enough (JSON `payload` + discriminator) that no migration is needed — explicitly stated either way in the phase plan.
  6. ADR-001 transitions Locked → Superseded; ADR-007 (PydanticAI) becomes Locked.

### Phase 7: Real Flight API
**Goal**: The agent calls Amadeus through the existing `FlightAPIClient` ABC, with `pyreqwest` for outbound HTTP, retry + circuit breaker, and clean error mapping; the mock remains the test default.
**Depends on**: Phase 6
**Requirements**: REQ-real-flight-api
**Success Criteria** (what must be TRUE):
  1. An Amadeus client implements `FlightAPIClient`, uses **`pyreqwest`** for async I/O (not `aiohttp`/`httpx`), and reuses the existing retry decorator (exponential backoff + circuit breaker) and `APIError` hierarchy.
  2. With real credentials configured, `search_flights` returns live results in the vendor-neutral JSON contract from Phase 4.6; without credentials, the system falls back to the mock client.
  3. Real-API integration tests exist and are gated on the `AMADEUS_*` secrets being present in the E2E job; PR CI does not require API keys.
  4. Default `pytest` continues to pass with the mock client as the DI default; documentation describes credential setup for local and CI use.
**Plans**: TBD

### Phase 8: Production Hardening (slim)
**Goal**: The demo is production-ready: hardened HTTP layer, structured logs, Chakra-aware markdown sanitization, and an 80% backend / 70-branch-80-line frontend coverage gate enforced in CI. **No rate limiting** (ADR-009).
**Depends on**: Phase 7
**Requirements**: REQ-security-headers, REQ-structured-logging, REQ-backend-test-coverage-60, REQ-coverage-ratchet-80
**Success Criteria** (what must be TRUE):
  1. Every response carries CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and Permissions-Policy headers; if the deployment splits backend + frontend onto different origins, CORS uses `settings.cors_origins` (wildcard forbidden).
  2. All `<ReactMarkdown>` instances run through `rehype-sanitize` with the custom Chakra-aware `sanitizeConfig.ts`: `<script>alert(1)</script>` in LLM output renders as escaped text and Chakra-rendered flight tables continue to render correctly.
  3. `structlog` JSON logging is configured at startup; `RequestLoggingMiddleware` issues a `request_id` per request; `ChatService` logs tool calls, streaming durations, and errors with `request_id` and `session_id`.
  4. CI enforces `pytest --cov=app --cov-fail-under=80` and frontend `coverage: { branches: 70, lines: 80 }`; new tests cover validation branches, model validators, and middleware.
  5. A security review of the production-mode demo finds zero CRITICAL findings; a user can log in, switch LLM providers from the UI, and receive structured, sanitized flight results from the real API end-to-end.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4.1 → 4.2 → 4.3 → 4.4 → 4.5 → 4.6 → 4.7 → 4.8 → 5 → 6 → 7 → 8.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation & FastAPI Setup | v0 | retro / retro | Partial (login UI + CI reset reopened) | 2025-11-08 |
| 2. LangChain Integration & Chat Agent | v0 | retro / retro | Complete | 2025-11-10 |
| 3. Mock Flight Search Tool | v0 | retro / retro | Complete | 2025-11-14 |
| 4.1. LLM Provider UI Config | v0 | retro / retro | Partial (wiring broken, reopened in 4.2) | 2026-05-13 |
| 4.2. Unbreak the App | v1 | 0 / TBD | Not started | - |
| 4.3. CI Reset | v1 | 0 / TBD | Not started | - |
| 4.4. Mock Chat in Tests | v1 | 0 / TBD | Not started | - |
| 4.5. LLM Provider Abstraction (real) | v1 | 0 / TBD | Not started | - |
| 4.6. Vendor-Neutral Tool JSON | v1 | 0 / TBD | Not started | - |
| 4.7. Error Handling + StreamEvent Hierarchy | v1 | 0 / TBD | Not started | - |
| 4.8. Validators + Test Hygiene + Orphan Cleanup | v1 | 0 / TBD | Not started | - |
| 5. Postgres + Redis + docker-compose | v1.5 | 0 / TBD | Not started | - |
| 6. PydanticAI Migration | v1.5 | 0 / TBD | Not started | - |
| 7. Real Flight API | v2 | 0 / TBD | Not started | - |
| 8. Production Hardening (slim) | v2 | 0 / TBD | Not started | - |

## Coverage

All 23 v1 requirements (3 validated + 3 partial-reopened + 17 active) map to exactly one phase. See `REQUIREMENTS.md` Traceability table for the full ID-to-phase mapping. No orphans; no duplicates.

---
*Roadmap created: 2026-05-14 by `gsd-roadmapper`. Last updated: 2026-05-15 after PR #6 review — phases renumbered to 4.2–4.8 + 5–8; v1 expanded to include Postgres+compose (Phase 5), PydanticAI migration (Phase 6); rate limiting dropped; `aiohttp` → `pyreqwest`; partial Phase 4.1 / auth / CI shipments status-corrected. Follow-up adversarial pass added `REQ-lint-line-length-120` + `REQ-annotated-depends` to Phase 4.3, named acceptance fixture sources for Phase 4.6, and added rework-risk/spike notes to Phases 4.5 / 5 / 6.*
