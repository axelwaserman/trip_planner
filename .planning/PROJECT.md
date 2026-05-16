# Trip Planner

## What This Is

An AI-powered trip-planning assistant with a conversational chat interface and real-time travel-data tool calls. A FastAPI backend orchestrates a streaming LangChain 1.0 agent that calls flight-search tools and surfaces structured results to a React + Chakra UI v3 frontend over Server-Sent Events. Currently a learning/demo project — not yet a production-deployed product.

## Core Value

**A user can authenticate via a real login page, pick an LLM provider (a local Ollama model discovered from the host, or a cloud provider via API key), hold a natural conversation with the agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully.**

If everything else fails, login → provider selection → streaming chat with tool visibility (content / thinking / tool_call / tool_result) must work end-to-end.

## Requirements

### Validated

<!-- Shipped in Phases 1-3, plus the engineering-quality PRs #1, #3, #5 that landed alongside.
     Phase 4.1 + auth + CI shipped *partially* — see "Partial / Broken" bucket below. -->

- ✓ Project foundation: Python 3.13 + uv, FastAPI, ruff/mypy/pytest, Vite + React + TS + Chakra UI v3, justfile — Phase 1
- ✓ LangChain 1.0 chat agent with `bind_tools()`, Ollama integration, SSE streaming, session-based history — Phase 2
- ✓ Mock flight-search tool: Pydantic models, abstract client pattern, LangChain `@tool`, frontend `ToolExecutionCard` + `ThinkingCard`, qwen3:4b reasoning mode — Phase 3
- ✓ Bug-fix + cleanup pass on routes / chat service / tests — PR #1 (REQ-bug-fixes-cleanup)
- ✓ Vitest + frontend testing infra; `ChatInterface.tsx` decomposed into `parseSSE` + `useSSEStream` + `useChat` hooks — PR #3 (REQ-frontend-testing-refactor; hooks-shape variant)
- ✓ mypy strict-mode fixes + ESLint cleanup — PR #5 (REQ-mypy-eslint-cleanup)
- ✓ CI reset — Backend / Frontend / E2E peer required-for-merge jobs on every PR push, no nightly schedule, no Ollama; ruff `line-length=120` + project-wide reformat; `Annotated[T, Depends(...)]` on all FastAPI routes — Phase 4.3 (REQ-ci-reset, REQ-lint-line-length-120, REQ-annotated-depends)

### Partial / Broken

<!-- Shipped on master but the app is *not currently usable in a browser*.
     v1 begins by unbreaking these (Phase 4.2). -->

- ⚠️ **REQ-auth-backend** — JWT via `pyjwt` + `pwdlib[argon2]`, `POST /token`, protected routes via `Depends(get_current_active_user)`, `AUTH_USERS` env-seeded users — PR #4. **Backend ships; no frontend login page exists, so every `/api/*` call returns 401 in the browser.**
- ⚠️ **REQ-llm-provider-ui-config** — `GET /api/providers`, `POST /api/chat/session` accepts `{provider, model}`, frontend dropdown, localStorage persistence — Phase 4.1. **UI ships but the model selector does not produce a working session — wiring is broken.**
- ✓ **REQ-ci-cd-pipeline** — GitHub Actions CI (backend + frontend) + branch protection — PR #2 (initial), Phase 4.3 (reset). Nightly schedule dropped, Ollama removed, E2E retained as a symbolic always-pass gate; real auth-flow + travel-API coverage deferred to later phases.

### Active

<!-- v1 milestone scope: unbreak the app, then re-platform onto Postgres + docker-compose,
     then PydanticAI, then real travel API, then hardening.
     Numbered phases match ROADMAP.md and REQUIREMENTS.md exactly. -->

- [ ] **REQ-login-page** — React login route, login form, token storage, protected routing, "logged-in user" affordance; quick-and-dirty backend user source (still env-seeded for now) (Phase 4.2)
- [ ] **REQ-llm-provider-ui-fix** — Restore working session creation when a provider/model is picked from the UI; deterministic error surface when the chosen provider is misconfigured (Phase 4.2)
- [ ] **REQ-mock-chat-tests** — Replace Ollama-bound chat tests with a `MockLLMStream` fixture; default `pytest` no longer requires Ollama; remove the `slow` marker; document the unit / integration / e2e split by purpose (Phase 4.4)
- [ ] **REQ-llm-provider-abstraction** — `LLMProvider` Protocol + `LLMProviderFactory`; **dynamic Ollama model discovery from the host** (no hard-coded list); **cloud-LLM API key path** (OpenAI + Anthropic, real implementations not stubs) supplied via env or session payload; per-session provider injection into `ChatService` (Phase 4.5)
- [ ] **REQ-tool-json-output** — `search_flights()` returns a vendor-neutral JSON shape designed to map cleanly onto Amadeus / Skyscanner / Google Flights responses (IATA + city for endpoints, ISO-8601 datetimes with timezone, `segments[]` for multi-leg, `price: {amount, currency}`); `ToolExecutionCard` renders tables / lists / nested objects (Phase 4.6)
- [ ] **REQ-error-handling-feedback** — UX-grade error feedback in the chat UI: API/session/tool error messages, loading states for tool execution, retry, toast notifications (Phase 4.7)
- [ ] **REQ-streamevent-hierarchy** — Replace monolithic `StreamEvent` with discriminated union `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`; update SSE serialization + frontend parsing (Phase 4.7)
- [ ] **REQ-pydantic-validators** — `Flight.arrival > departure`, `FlightQuery.departure_date >= today`, `FlightQuery.origin != destination` — additive to the existing `validate_dates` validator (Phase 4.8)
- [ ] **REQ-test-fixture-dedup** — Shared `create_mock_flight()` factory and `parse_sse_events()` helper; refactor existing tests to consume them; delete orphaned `ToolCallCard.tsx` / `ToolResultCard.tsx` (Phase 4.8)
- [ ] **REQ-postgres-redis-compose** — `docker-compose.yml` brings up backend + frontend + Postgres + Redis with named volumes and a single `OLLAMA_BASE_URL` override; `psycopg` async + `sqlmodel` ORM for `User` / `Session` / `Message`; users seeded from PG (replaces `AUTH_USERS` env-var workaround); CORS resolved by the compose network (Phase 5)
- [ ] **REQ-pydantic-ai-migration** — Port `ChatService` from LangChain `bind_tools()` to PydanticAI agents while preserving the SSE event contract; remove `langchain` / `langchain-ollama` from `pyproject.toml`; ADR-001 transitions Locked → Superseded (Phase 6)
- [ ] **REQ-real-flight-api** — Replace `MockFlightAPIClient` with a real flight provider (Amadeus) behind the existing `FlightAPIClient` ABC; outbound HTTP via **`pyreqwest`** (not `aiohttp`); reuse retry + circuit breaker + `APIError` hierarchy; gated integration tests (Phase 7)
- [ ] **REQ-security-headers** — CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy on every response; CORS allowlist from `settings.cors_origins` if not already solved by the compose network; `rehype-sanitize` with the custom Chakra-aware config (Phase 8)
- [ ] **REQ-structured-logging** — `structlog` JSON logging; `RequestLoggingMiddleware` issues a `request_id`; `ChatService` logs tool calls, streaming durations, and errors with `request_id` + `session_id` (Phase 8)
- [ ] **REQ-backend-test-coverage-60** — Reach 60% backend coverage with no-network / no-Ollama tests (Phase 8)
- [ ] **REQ-coverage-ratchet-80** — Raise CI threshold to `--cov-fail-under=80`; frontend `coverage: { branches: 70, lines: 80 }` (Phase 8)

### Out of Scope

<!-- Explicit boundaries with reasoning, to prevent re-adding. -->

- **Rate limiting (`slowapi` or otherwise)** — Dropped from v1 hardening. Demo-grade traffic does not warrant it; revisit only if the project ever gets a public deployment surface.
- **REQ-session-management refactor** / **REQ-di-lifespan-fix** — Superseded. Postgres + `app.state` lifespan singletons (Phase 5) are the durable answer; the old "introduce SessionStore ABC" / "replace `@lru_cache` with `app.state`" refactor RFCs are obsolete on either count.
- **Default-config rehype-sanitize variant** (pre-phase-4-refactor Task 10) — Superseded by the Chakra-aware custom-config variant (Phase 8 / REQ-security-headers). Default config strips Chakra table elements and silently regresses flight-result rendering.
- **Reducer-based ChatInterface decomposition** (pre-phase-4-refactor Task 5) — Superseded by the hooks-shape decomposition shipped in PR #3.
- **`openapi-typescript` codegen for frontend types** — Better long-term than hand-written `types/chat.ts`, but premature until the API contract stabilizes; revisit after Phase 6.
- **Playwright frontend E2E** — Defer until Phase 4 stabilizes the component surface.
- **JWT token revocation / deny-list** — Mitigated by 60-min expiry; full DB-backed revocation is post-v1.
- **User registration endpoint** — Internal/demo project; users are seeded (env-var workaround in Phase 4.2, Postgres-seeded from Phase 5 onward).
- **Additional travel tools (hotels, restaurants, weather)** — v1 covers flights only.
- **Multi-city / multi-leg trip planning** — v1 covers single origin/destination/date queries.
- **DSPy / GraphQL migration** — Architectural pivots, not in scope. (PydanticAI is the architectural pivot v1 *does* take, in Phase 6.)

## Context

**Codebase state.** Brownfield, **non-functional in the browser as of 2026-05-15**: chat requests return 401 because no frontend login route ships, and the in-UI provider/model selector does not produce a working session. The repository has shipped Phases 1-3 plus the partial Phase 4.1 surface (UI without working wiring), plus engineering-quality PRs #1, #3, #5 (#2 and #4 shipped but partial — see Partial / Broken bucket above). Authoritative onboarding doc is `CLAUDE.md` (the legacy `README.md` references `gpt-oss20b`, `PLAN.md`, and `copilot-instructions.md` — all stale). v1 begins by unbreaking auth and the model selector (Phase 4.2).

**Two parallel phasing schemes existed pre-ingest.** The legacy product roadmap (Phase 1 Foundation → Phase 6 Production Readiness) and the engineering plan (Phase 0 Bug Fixes → Phase 6 Coverage 80%) shared phase numbers. Per user direction, **the product-phase numbering scheme is authoritative**. Engineering items now live inside the renumbered phase tree (4.2 Unbreak App → 4.8 → 5 Postgres+compose → 6 PydanticAI → 7 Real API → 8 Hardening); there is no parallel "engineering Phase N" track.

**Architectural philosophy.** Async-first, type-safe, dependency-injected, SOLID. Comments answer *why*, never *what*. Default `pytest` is fast and **does not call Ollama** — chat tests use a `MockLLMStream` fixture (delivered in Phase 4.4). Test roles: **unit** = pure functions / in-process logic, no external services; **integration** = FastAPI test client + (post-Phase-5) PG container + mock LLM stream + mock travel API; **E2E** = real auth login flow + real travel API only, gated on credentials.

**Named patterns** (locked through Phase 5; ADR-001 LangChain → Superseded in Phase 6, see `ARCHITECTURE.md` and ADRs below):
- Data Model Pattern — Pydantic models, no business logic except validators.
- Abstract Client Pattern — `BaseAPIClient (ABC) → FlightAPIClient (ABC) → MockFlightAPIClient | <RealProvider>`. Async only. Retry + circuit breaker + custom exception hierarchy. Real client uses `pyreqwest` (Phase 7).
- Functional Service Pattern — pure async functions; cross-cutting concerns via decorators.
- Dependency Injection Pattern — FastAPI `Depends()` parameters today; **target**: `Annotated[T, Depends(...)]` (lands in Phase 4.3 alongside the CI reset). Singletons live in `app.state` (lifespan-managed); never `@lru_cache`.

**Frontend** — `App.tsx` (layout + session init), `ChatInterface.tsx` (post PR #3 hooks-shape decomposition), `ToolExecutionCard.tsx`, `ThinkingCard.tsx`. Phase 4.2 adds a `Login.tsx` route + protected-route wrapper. Vite proxies `/api/*` to `localhost:8000`. `ToolCallCard.tsx` + `ToolResultCard.tsx` are candidates for deletion in Phase 4.8 — verify no remaining imports before deletion.

**Workflow.** GSD framework: `/gsd-discuss-phase`, `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-progress`. Project-local skills: `/fastapi`, `/chakra-ui`, `/pydantic-ai-agent-builder`. All ops via `just`.

**Known accepted limitations** (mitigations in place; not bugs to fix):
- No JWT token revocation — 60-min expiry, rotate `jwt_secret` on breach.
- `AUTH_USERS` env-seeded user store is a Phase 4.2 quick-and-dirty workaround; replaced by PG-seeded users in Phase 5.
- E2E tests run only when credentials are present (auth flow + real travel API). Removed from default CI; not nightly-scheduled.
- `search_flights._flight_client` monkey-patch retained — works, contained, refactor when adding more tools.

## Constraints

- **Tech stack — runtime**: Python 3.13 backend (uv), Node 22 frontend (npm). CI pins these versions; no `engines.node` field in `frontend/package.json` enforces it for local dev.
- **Tech stack — frameworks**: FastAPI ≥ 0.120, Pydantic ≥ 2.12, React ≥ 18, TypeScript ≥ 5, Chakra UI v3, Vite, react-markdown + remark-gfm. **LangChain 1.0** is the current chat agent runtime through Phase 5; **PydanticAI** replaces it in Phase 6 (rationale: lighter, easier to test).
- **LLM access**: v1 supports two paths, both selectable per session: (a) **dynamic Ollama model discovery** from the host (no hard-coded default; `OLLAMA_BASE_URL` configurable); (b) **cloud LLM via API key** (OpenAI, Anthropic), supplied by env var or session creation payload. Stub-only providers are not acceptable. The legacy `init_chat_model(reasoning=True)` qwen3:4b path remains available as one of many local models.
- **Async I/O only**: All I/O is `async def`. No `requests`. No sync file I/O on async paths. **Outbound HTTP uses `pyreqwest`** (not `aiohttp`/`httpx`) from Phase 7 onward; **database access uses `psycopg` async + `sqlmodel` ORM** from Phase 5 onward.
- **Type safety**: `mypy` runs in strict mode. Bare `type: ignore` is forbidden — every ignore must include an explanatory comment.
- **Package manager**: `uv` exclusively for Python — never `pip`, `poetry`, `conda`.
- **Lint/format**: `ruff` line length **100 today; target 120** (lands in Phase 4.3 alongside the CI reset); `isort` first-party prefix `app`; `ruff check` and `ruff format --check` must pass in CI.
- **Test layout**: `backend/tests/{unit,integration,e2e}` with markers `@pytest.mark.unit`, `.integration`, `.e2e`. The `slow` marker still exists in `pyproject.toml` today; it is **removed** in Phase 4.4 (REQ-mock-chat-tests) once chat tests no longer need Ollama gating. Default `pytest` does not require Ollama or network. **Unit** = pure functions / in-process logic, no external services. **Integration** = FastAPI test client + (post-Phase-5) PG container + mock LLM stream + mock travel API. **E2E** = real auth login flow + real travel API only, gated on credentials. AAA pattern with descriptive names.
- **Coverage gates**: 60% backend floor today; ratcheted to 80% in Phase 8. Frontend `coverage: { branches: 70, lines: 80 }` added in Phase 8.
- **CI** (Phase 4.3 reset): Triggers on `push` to any branch with an open PR plus `pull_request` to `master`. **No scheduled run.** Lint + unit + integration jobs must pass for merge — branch protection on `master` enforces this. The E2E job is retained but runs only when credentials secrets are present, and exercises auth flow + real travel API only (never Ollama).
- **Auth**: JWT via `pyjwt` + `pwdlib[argon2]`. `jwt_secret`, `jwt_algorithm = "HS256"`, `jwt_expire_minutes = 60`. **Phase 4.2**: a React login route hits `POST /token`; users are still seeded from `AUTH_USERS=user1:pass1,...` as a quick-and-dirty workaround. **Phase 5**: users move to a Postgres `users` table and `AUTH_USERS` is retired. Protected routes depend on `get_current_active_user`. `GET /health` is public; everything else requires auth.
- **CORS**: Today CORS is hard-coded in `api/main.py` with `allow_origins=["http://localhost:5173"]`. Phase 5's docker-compose network resolves CORS by collapsing backend + frontend onto a single origin. If any post-Phase-5 deployment splits origins, Phase 8's `settings.cors_origins` allowlist applies (wildcard `*` forbidden).
- **Security headers**: All responses must include CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy via dedicated middleware (delivered in Phase 8).
- **Markdown sanitization**: All `<ReactMarkdown>` instances must use `rehype-sanitize` with the **custom Chakra-aware `sanitizeConfig.ts`** that preserves table elements. The default config is forbidden (strips Chakra-rendered tables).
- **SSE protocol**: Server streams `StreamEvent` objects with `type` ∈ {`content`, `thinking`, `tool_call`, `tool_result`}; `thinking` chunks come from `chunk.additional_kwargs["reasoning_content"]`. Phase 4.7 replaces this with a discriminated union including `error`.
- **Singletons**: Lifespan-managed via `app.state`. `@lru_cache` is forbidden for singleton factories. Routes use bare `Depends()` today; the `Annotated[T, Depends(...)]` migration lands in Phase 4.3.
- **API contracts** (current, evolving in Phase 4.6 / 4.7):
  - `GET /api/providers` — providers + models + credential status
  - `POST /api/chat/session` — accepts `{"provider": "<id>", "model": "<id>"}`, returns 201
  - `DELETE /api/chat/session/{id}` — must remove `_histories[id]`, `_metadata[id]`, `_last_activity[id]`
  - `POST /api/chat/session` response shape: `{ "session_id": "<uuid>", "provider": "ollama", "model": "<discovered>" }` (`created_at` is stored internally only, not returned)

## Key Decisions

<!-- Locked ADRs and locked-by-implementation decisions. ADR-002 is recorded as Obsolete (never implemented + superseded by Phase 5 PG-backed history). -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **ADR-001** Use LangChain 1.0 `bind_tools()` (not `create_agent()`) | LangGraph under the hood; works with any chat model that supports function calling; simpler to mock/test; streaming works out of the box | ⚠️ **Superseded by ADR-007** — replaced by PydanticAI in Phase 6; rationale: lighter and easier to test. LangChain remains in place through Phase 5. |
| **ADR-002** Global `_global_chat_store` for session history | Per `NOW.md`, the premise was a misunderstanding — no `_global_chat_store` ever existed; `ChatService._histories` was per-instance from the start. | ⚠️ **Obsolete** — Phase 5 moves history into Postgres anyway, so the original ADR is doubly moot. Recorded for history only. |
| **ADR-003** Stream LLM responses via Server-Sent Events using FastAPI `StreamingResponse` | Native browser support, simpler than WebSockets for unidirectional streaming, FastAPI-friendly. | ✓ Locked-as-implemented (`StreamingResponse` in `routes.py`) |
| **ADR-004** Pydantic models for all data structures (no raw dicts) | Validation, OpenAPI schema generation, mypy integration, free serialization | ✓ Good — locked |
| **ADR-005** Mock-first external API (build `MockFlightAPIClient`, real Amadeus later) | Faster iteration, deterministic tests, no API credentials during dev | ✓ Good — locked; real client lands Phase 7 (after compose + PydanticAI re-platform) |
| **ADR-006** Postgres + `psycopg` async + `sqlmodel` ORM, in docker-compose, single spin-up | Replaces in-memory `_histories` and `AUTH_USERS` env-seed; named volumes survive restart; CORS resolved by single compose network; `OLLAMA_BASE_URL` overridable. **Pre-phase spike**: verify `postgresql+psycopg://` async URI works with SQLModel async session out-of-the-box on SQLAlchemy ≥ 2.0 (SQLModel historically targeted `asyncpg`; if `psycopg` async needs adapter glue, surface that before locking the model layer). | — Pending — lands Phase 5 |
| **ADR-007** PydanticAI replaces LangChain for the chat agent | Lighter footprint, easier to mock/test, native Pydantic integration; LangChain currently works but the migration is the cheaper long-term carrying cost | — Pending — lands Phase 6 |
| **ADR-008** `pyreqwest` for outbound HTTP (real travel APIs) | Async-first Rust-backed client, performance + ergonomics; replaces `aiohttp` references in earlier docs | — Pending — lands Phase 7 |
| **ADR-009** Drop rate limiting from v1 hardening | Demo-grade traffic does not warrant `slowapi` + key-function complexity; revisit only if a public deployment surface materializes | ✓ Decided — applies from Phase 8 onward |
| JWT auth via `pyjwt` + `pwdlib[argon2]` (HS256, 60-min expiry) | Standard, well-supported | ✓ Backend shipped PR #4 — login UI lands Phase 4.2; users move from `AUTH_USERS` env to PG in Phase 5 |
| `uv` exclusively for Python package management | Faster, lockfile-first, replaces `pip`/`poetry`/`conda` | ✓ Good — locked |
| `mypy` strict mode with annotated `type: ignore` only | Prevents silent type erosion | ✓ Good — locked |
| Lifespan-managed singletons in `app.state` (no `@lru_cache`); routes migrate to `Annotated[T, Depends(...)]` in Phase 4.3 | Proper FastAPI DI; testable without full lifespan; no module-level state; modern FastAPI idiom | Singletons ✓ shipped; Annotated DI — Pending (Phase 4.3) |
| Product-phase numbering authoritative; engineering items folded into the renumbered phase tree | Avoids parallel "Phase N" tracks | ✓ Good — applied at this synthesis |
| Hooks-shape `ChatInterface` decomposition (PR #3) over reducer-based variant | PR #3 already merged with the hooks variant; reducer variant has no remaining advantage | ✓ Good — superseded |
| Custom Chakra-aware `sanitizeConfig.ts` for `rehype-sanitize` (over default config) | Default config silently strips Chakra-rendered tables, regressing flight-result UX | — Pending — lands in Phase 8 |
| Adopt user-stated milestone goal: unbreak app → re-platform onto PG+compose → swap to PydanticAI → real travel API → hardening | User's success metric: working browser demo (login → provider select → chat → real flight results), 80% backend coverage, no CRITICAL security findings | — Pending — drives v1 roadmap |

---
*Last updated: 2026-05-16 after Phase 4.3 completion — CI reset shipped (Backend/Frontend/E2E peer required jobs, no schedule, no Ollama), ruff `line-length=120` + project-wide reformat, FastAPI routes migrated to `Annotated[T, Depends(...)]`. REQ-ci-reset / REQ-lint-line-length-120 / REQ-annotated-depends moved Active → Validated; REQ-ci-cd-pipeline reframed as ✓ shipped via PR #2 + Phase 4.3 reset.*

*2026-05-15: PR #6 review pass — promoted Postgres+compose & PydanticAI into v1, dropped rate limiting, status-corrected partial Phase 4.1 / auth / CI shipments, renumbered phases through Phase 8. Follow-up adversarial review then reframed declared-as-shipped targets (ruff 120, Annotated DI, `slow` marker) as Phase 4.3/4.4 deliverables, added rework-risk + sequencing notes around Phase 4.5 ↔ 5 ↔ 6, added a `psycopg`+SQLModel pre-phase spike to ADR-006, and named acceptance fixture sources for REQ-tool-json-output.*
