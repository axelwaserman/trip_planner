# Trip Planner

## What This Is

An AI-powered trip-planning assistant with a conversational chat interface and real-time travel-data tool calls. A FastAPI backend orchestrates a streaming LangChain 1.0 agent that calls flight-search tools and surfaces structured results to a React + Chakra UI v3 frontend over Server-Sent Events. Currently a learning/demo project — not yet a production-deployed product.

## Core Value

**A user can hold a natural conversation with an AI agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully — across multiple LLM providers selected from the UI.**

If everything else fails, the streaming chat with tool visibility (content / thinking / tool_call / tool_result) and provider switching must work end-to-end.

## Requirements

### Validated

<!-- Shipped in Phases 1-4.1, plus the engineering-quality PRs #1-#5 that landed alongside. -->

- ✓ Project foundation: Python 3.13 + uv, FastAPI, ruff/mypy/pytest, Vite + React + TS + Chakra UI v3, justfile — Phase 1
- ✓ LangChain 1.0 chat agent with `bind_tools()`, Ollama integration, SSE streaming, session-based history — Phase 2
- ✓ Mock flight-search tool: Pydantic models, abstract client pattern, LangChain `@tool`, frontend `ToolExecutionCard` + `ThinkingCard`, qwen3:4b reasoning mode — Phase 3
- ✓ LLM provider UI config: `GET /api/providers`, `POST /api/chat/session` accepts `{provider, model}`, frontend dropdown, localStorage persistence — Phase 4.1
- ✓ Bug-fix + cleanup pass on routes / chat service / tests — PR #1 (REQ-bug-fixes-cleanup)
- ✓ JWT auth via `pyjwt` + `pwdlib[argon2]`, protected routes, in-memory user store from `AUTH_USERS` env var — PR #4 (REQ-auth-hardening)
- ✓ GitHub Actions CI (backend + frontend; E2E gated to `workflow_dispatch`/`schedule`); branch protection on master — PR #2 (REQ-ci-cd-pipeline)
- ✓ Vitest + frontend testing infra; `ChatInterface.tsx` decomposed into `parseSSE` + `useSSEStream` + `useChat` hooks — PR #3 (REQ-frontend-testing-refactor; hooks-shape variant)
- ✓ mypy strict-mode fixes + ESLint cleanup — PR #5

### Active

<!-- v1 milestone scope: complete Phase 4 (Provider Flexibility + UI Polish), reach a production-ready demo. -->

- [ ] **REQ-tool-json-output** — `search_flights()` returns structured JSON with `status`, `query`, `results[]` (flight_number, airline, route, departure, arrival, duration_hours, price_usd, stops), `count`; `ToolExecutionCard` renders tables/lists/nested objects (Phase 4.2)
- [ ] **REQ-error-handling-feedback** — UX-grade error feedback in the chat UI: API/session/tool error messages, loading states for tool execution, retry, toast notifications (Phase 4.3)
- [ ] **REQ-streamevent-hierarchy** — Replace monolithic `StreamEvent` with discriminated union `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`; update SSE serialization + frontend parsing (Phase 4.3)
- [ ] **REQ-llm-provider-abstraction** — Formalize `LLMProvider` Protocol + `OllamaProvider` + `LLMProviderFactory`; per-session provider injection into `ChatService` (Phase 4.4)
- [ ] **REQ-pydantic-validators** — `Flight.arrival_time > departure_time`, `FlightQuery.departure_date >= today`, `FlightQuery.origin != destination` (Phase 4.4)
- [ ] **REQ-test-fixture-dedup** — Shared `create_mock_flight()` factory and `parse_sse_events()` helper; refactor existing tests to consume them (Phase 4.4)
- [ ] **REQ-real-flight-api** — Replace `MockFlightAPIClient` with a real flight provider (Amadeus or equivalent) behind the existing `FlightAPIClient` ABC; retry, circuit breaker, error mapping (Phase 5)
- [ ] **REQ-security-hardening** — CSP / X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy headers; CORS allowlist from env; `slowapi` rate limiting with `X-Forwarded-For`-aware key; `rehype-sanitize` with custom Chakra-aware config in `<ReactMarkdown>` (Phase 6)
- [ ] **REQ-structured-logging** — `structlog` + `RequestLoggingMiddleware`; per-request `request_id`; `ChatService` logs tool calls / streaming durations / errors with full context (Phase 6)
- [ ] **REQ-backend-test-coverage-60** — Reach 60% backend coverage with no-network / no-Ollama tests; `test_chat_service.py`, `test_auth.py`, `test_config.py`, `test_routes.py` (Phase 6)
- [ ] **REQ-coverage-ratchet-80** — Raise CI threshold to `--cov-fail-under=80`; frontend coverage `{ branches: 70, lines: 80 }`; new `test_flight_search.py` validation branches, `test_models.py` validators, `test_middleware.py` (Phase 6)

### Out of Scope

<!-- Explicit boundaries with reasoning, to prevent re-adding. -->

- **REQ-session-management refactor** — Premise was wrong: `ChatService._histories` already provides per-instance session storage; no global `_global_chat_store` ever existed (`NOW.md` 2025-11-14, `CLAUDE.md`).
- **REQ-di-lifespan-fix** — Premise was wrong: singletons already live in `app.state` via the FastAPI `lifespan` context manager; no `@lru_cache` factories exist (`NOW.md` 2025-11-14, `CLAUDE.md`).
- **Default-config rehype-sanitize variant** (pre-phase-4-refactor Task 10) — Superseded by the Chakra-aware custom-config variant (Phase 6 / REQ-security-hardening). Default config strips Chakra table elements and silently regresses flight-result rendering.
- **Reducer-based ChatInterface decomposition** (pre-phase-4-refactor Task 5) — Superseded by the hooks-shape decomposition shipped in PR #3.
- **Database persistence (PostgreSQL)** — In-memory sessions sufficient for MVP demo; defer until persistence-across-restart is a real user need.
- **Docker / docker-compose packaging** — Defer until CI green + auth stable + first deployment target chosen; must override `OLLAMA_BASE_URL` (cannot use `localhost` from inside container).
- **`openapi-typescript` codegen for frontend types** — Better long-term than hand-written `types/chat.ts`, but premature until the API contract stabilizes.
- **Playwright frontend E2E** — Defer until after Phase 4 component refactor stabilizes.
- **JWT token revocation / deny-list** — Mitigated by 60-min expiry; full DB-backed revocation is post-MVP scope.
- **Redis-backed rate limiter** — Single-process in-memory limiter is acceptable for the demo; add Redis when horizontally scaling.
- **User registration endpoint** — Internal/demo project; users are seeded from `AUTH_USERS` env var.
- **Additional travel tools (hotels, restaurants, weather)** — Out of v1 scope; Phase 5+ belongs to flights only.
- **Multi-city trip planning** — v1 covers single origin/destination/date queries.
- **DSPy / GraphQL migration** — Architectural pivots, not in scope.

## Context

**Codebase state.** Brownfield. The repository has shipped Phases 1-3 of the product roadmap and sub-phase 4.1, plus engineering-quality PRs #1-#5. Authoritative onboarding doc is `CLAUDE.md` (the legacy `README.md` references `gpt-oss20b`, `PLAN.md`, and `copilot-instructions.md` — all stale). Current default LLM is **qwen3:4b** via Ollama with `init_chat_model(reasoning=True)`.

**Two parallel phasing schemes existed pre-ingest.** The legacy product roadmap (Phase 1 Foundation → Phase 6 Production Readiness) and the engineering plan (Phase 0 Bug Fixes → Phase 6 Coverage 80%) shared phase numbers. Per user direction, **the product-phase numbering scheme is authoritative**. Engineering-plan items have been re-classified as a cross-cutting **Quality Workstream** that lands in Phases 4.4 / 5 / 6 alongside product features.

**Architectural philosophy.** Async-first, type-safe, dependency-injected, SOLID. Comments answer *why*, never *what*. Test split target: unit 70% / integration 20% / E2E 10%. Default `pytest -m "not slow"` is fast and excludes Ollama-dependent E2E.

**Named patterns** (locked, see `ARCHITECTURE.md` and ADRs below):
- Data Model Pattern — Pydantic models, no business logic except validators.
- Abstract Client Pattern — `BaseAPIClient (ABC) → FlightAPIClient (ABC) → MockFlightAPIClient | <RealProvider>`. Async only. Retry + circuit breaker + custom exception hierarchy.
- Functional Service Pattern — pure async functions; cross-cutting concerns via decorators.
- Dependency Injection Pattern — FastAPI `Depends()`; singletons in `app.state` (lifespan-managed); never `@lru_cache`.

**Frontend** — `App.tsx` (layout + session init), `ChatInterface.tsx` (post PR #3 hooks-shape decomposition), `ToolExecutionCard.tsx`, `ThinkingCard.tsx`. Vite proxies `/api/*` to `localhost:8000`. Orphaned `ToolCallCard.tsx` + `ToolResultCard.tsx` slated for deletion in Phase 4.4.

**Workflow.** GSD framework: `/gsd-discuss-phase`, `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-progress`. Project-local skills: `/fastapi`, `/chakra-ui`, `/pydantic-ai-agent-builder`. All ops via `just`.

**Known accepted limitations** (mitigations in place; not bugs to fix):
- No JWT token revocation — 60-min expiry, rotate `jwt_secret` on breach.
- In-memory sessions lost on restart — acceptable for MVP.
- Rate limiter resets on restart, single-process — Redis backend deferred.
- E2E tests require Ollama, not in PR CI — gated to manual/scheduled workflow.
- `search_flights._flight_client` monkey-patch retained — works, contained, refactor when adding more tools.

## Constraints

- **Tech stack — runtime**: Python 3.13 backend (uv), Node 22 frontend (npm) — CI pins these versions; README's "Node 20+" is a lower bound, not the operational target.
- **Tech stack — frameworks**: FastAPI ≥ 0.120, LangChain ≥ 1.0 (with LangGraph), Pydantic ≥ 2.12, React ≥ 18, TypeScript ≥ 5, Chakra UI v3, Vite, react-markdown + remark-gfm — locked by ADR-001 and existing code.
- **LLM**: Default model is `qwen3:4b` via Ollama, accessed through `init_chat_model(reasoning=True)` for thinking-token support — confirmed by `NOW.md`, `CLAUDE.md`, `CI_CD_WORKFLOW.md`. `gpt-oss20b` and `qwen3:8b` references in older docs are stale.
- **Async I/O only**: All I/O is `async def`. No `requests`. No sync file I/O on async paths. (`CLAUDE.md`)
- **Type safety**: `mypy` runs in strict mode. Bare `type: ignore` is forbidden — every ignore must include an explanatory comment. (`CLAUDE.md`)
- **Package manager**: `uv` exclusively for Python — never `pip`, `poetry`, `conda`. (`CLAUDE.md`)
- **Lint/format**: `ruff` line length 100; `isort` first-party prefix `app`; `ruff check` and `ruff format --check` must pass in CI. (`CLAUDE.md`, `CI_CD_WORKFLOW.md`)
- **Test layout**: `backend/tests/{unit,integration,e2e}` with markers `@pytest.mark.unit`, `.integration`, `.e2e`, `.slow`. Default `pytest` excludes `slow`. AAA pattern with descriptive names. No test in default suite may require network or Ollama.
- **Coverage gates**: 60% floor active now via PR #2's CI; ratchet to 80% in Phase 6. Frontend coverage thresholds `{ branches: 70, lines: 80 }` added in Phase 6.
- **CI**: Branch protection on `master` requires `Backend (Python 3.13)` and `Frontend (Node 22)` jobs. `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }`. E2E job is `workflow_dispatch` / `schedule` only.
- **Auth**: JWT via `pyjwt` + `pwdlib[argon2]`. `jwt_secret`, `jwt_algorithm = "HS256"`, `jwt_expire_minutes = 60`. Users seeded from `AUTH_USERS=user1:pass1,...`. Protected routes depend on `get_current_active_user`. `GET /health` is public; everything else requires auth.
- **CORS**: `settings.cors_origins` (default `["http://localhost:5173"]`). Wildcard `*` is forbidden.
- **Security headers**: All responses must include CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy via dedicated middleware (delivered in Phase 6).
- **Rate limiting**: `slowapi` with `X-Forwarded-For`-aware key; per-user limits; 429 over threshold; in-memory only (Redis deferred).
- **Markdown sanitization**: All `<ReactMarkdown>` instances must use `rehype-sanitize` with the **custom Chakra-aware `sanitizeConfig.ts`** that preserves table elements. The default config is forbidden (it strips Chakra-rendered tables).
- **SSE protocol**: Server streams `StreamEvent` objects with `type` ∈ {`content`, `thinking`, `tool_call`, `tool_result`}; `thinking` chunks come from `chunk.additional_kwargs["reasoning_content"]`. Phase 4.3 replaces this with a discriminated union including `error`.
- **Singletons**: Lifespan-managed via `app.state`. `@lru_cache` is forbidden for singleton factories.
- **API contracts** (locked):
  - `GET /api/providers` — providers + models + credential status
  - `POST /api/chat/session` — accepts `{"provider": "<id>", "model": "<id>"}`, returns 201
  - `DELETE /api/chat/session/{id}` — must remove `_histories[id]`, `_metadata[id]`, `_last_activity[id]`
  - Session metadata shape: `{ "provider": "ollama", "model": "qwen3:4b", "created_at": "<epoch>" }`

## Key Decisions

<!-- Locked ADRs and locked-by-implementation decisions. ADR-002 is recorded as Deprecated/historical. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **ADR-001** Use LangChain 1.0 `bind_tools()` (not `create_agent()`) | LangGraph under the hood; works with any chat model that supports function calling; simpler to mock/test; streaming works out of the box | ✓ Good — locked |
| **ADR-003** Stream LLM responses via Server-Sent Events (`EventSourceResponse`) | Native browser support, simpler than WebSockets for unidirectional streaming, FastAPI-friendly | ✓ Good — locked |
| **ADR-004** Pydantic models for all data structures (no raw dicts) | Validation, OpenAPI schema generation, mypy integration, free serialization | ✓ Good — locked |
| **ADR-005** Mock-first external API (build `MockFlightAPIClient`, real Amadeus later) | Faster iteration, deterministic tests, no API credentials during dev | ✓ Good — locked; real client lands Phase 5 |
| **ADR-002** Global `_global_chat_store` for session history | (Was: simplest way to persist sessions across requests) | ⚠️ **Deprecated** — superseded by `ChatService._histories` (per-instance). Recorded for history; not active. |
| JWT auth via `pyjwt` + `pwdlib[argon2]` (HS256, 60-min expiry, env-seeded users) | Standard, well-supported, no DB needed for demo | ✓ Good — shipped PR #4 |
| `uv` exclusively for Python package management | Faster, lockfile-first, replaces `pip`/`poetry`/`conda` | ✓ Good — locked |
| `mypy` strict mode with annotated `type: ignore` only | Prevents silent type erosion | ✓ Good — locked |
| Lifespan-managed singletons in `app.state` (no `@lru_cache`) | Proper FastAPI DI; testable without full lifespan; no module-level state | ✓ Good — locked |
| Product-phase numbering authoritative; engineering items as cross-cutting Quality Workstream | Two parallel "Phase N" schemes confused readers; product-phase is the user-facing milestone arc | ✓ Good — applied at this synthesis |
| Hooks-shape `ChatInterface` decomposition (PR #3) over reducer-based variant | PR #3 already merged with the hooks variant; reducer variant has no remaining advantage | ✓ Good — superseded |
| Custom Chakra-aware `sanitizeConfig.ts` for `rehype-sanitize` (over default config) | Default config silently strips Chakra-rendered tables, regressing flight-result UX | — Pending — lands in Phase 6 |
| Adopt user-stated milestone goal: Phase 4 (Provider Flexibility + UI Polish) → ship production-ready demo | User's success metric: tests green + 80% backend coverage + zero CRITICAL security findings + working LLM-provider switching from UI + real-API flight integration | — Pending — drives v1 roadmap |

---
*Last updated: 2026-05-14 after `gsd-roadmapper` synthesis from `.planning/intel/SYNTHESIS.md` (mode: new-project-from-ingest).*
