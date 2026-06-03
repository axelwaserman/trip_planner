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
- ✓ LLM provider abstraction — `LLMProvider` Protocol + `LLMProviderFactory`; dynamic Ollama model discovery via `GET /api/tags`; real OpenAI + Anthropic + LM Studio providers (env or session payload key); per-session provider injection into `ChatService`; minimal API-key log scrubber; per-user session partitioning; settings UI with active-model badge — Phase 4.5 (REQ-llm-provider-abstraction)

### Partial / Broken

<!-- Shipped on master but the app is *not currently usable in a browser*.
     v1 begins by unbreaking these (Phase 4.2). -->

- ⚠️ **REQ-auth-backend** — JWT via `pyjwt` + `pwdlib[argon2]`, `POST /token`, protected routes via `Depends(get_current_active_user)`, `AUTH_USERS` env-seeded users — PR #4. **Backend ships; no frontend login page exists, so every `/api/*` call returns 401 in the browser.**
- ⚠️ **REQ-llm-provider-ui-config** — `GET /api/providers`, `POST /api/chat/session` accepts `{provider, model}`, frontend dropdown, localStorage persistence — Phase 4.1. **UI ships but the model selector does not produce a working session — wiring is broken.**
- ✓ **REQ-ci-cd-pipeline** — GitHub Actions CI (backend + frontend) + branch protection — PR #2 (initial), Phase 4.3 (reset). Nightly schedule dropped, Ollama removed, E2E retained as a symbolic always-pass gate; real auth-flow + travel-API coverage deferred to later phases.

### Active

<!-- v1 milestone scope: unbreak the app, then migrate to PydanticAI, then re-platform
     onto Postgres + docker-compose, then real travel API, then hardening.
     Phase 5 ↔ Phase 6 swap (PydanticAI ahead of Postgres) was made on 2026-06-02
     per PR #20 review.
     Numbered phases match ROADMAP.md and REQUIREMENTS.md exactly. -->

- [ ] **REQ-login-page** — React login route, login form, token storage, protected routing, "logged-in user" affordance; quick-and-dirty backend user source (still env-seeded for now) (Phase 4.2)
- [ ] **REQ-llm-provider-ui-fix** — Restore working session creation when a provider/model is picked from the UI; deterministic error surface when the chosen provider is misconfigured (Phase 4.2)
- [x] **REQ-mock-chat-tests** — Replace Ollama-bound chat tests with a `MockLLMStream` fixture; default `pytest` no longer requires Ollama; remove the `slow` marker; document the unit / integration / e2e split by purpose (Phase 4.4) — Validated in Phase 4.4
- [x] **REQ-llm-provider-abstraction** — `LLMProvider` Protocol + `LLMProviderFactory`; **dynamic Ollama model discovery from the host** (no hard-coded list); **cloud-LLM API key path** (OpenAI + Anthropic + LM Studio, real implementations not stubs) supplied via env or session payload; per-session provider injection into `ChatService` (Phase 4.5) — Validated in Phase 4.5
- [ ] **REQ-tool-json-output** — `search_flights()` returns a vendor-neutral JSON shape designed to map cleanly onto Amadeus / Skyscanner / Google Flights responses (IATA + city for endpoints, ISO-8601 datetimes with timezone, `segments[]` for multi-leg, `price: {amount, currency}`); `ToolExecutionCard` renders tables / lists / nested objects (Phase 4.6)
- [ ] **REQ-error-handling-feedback** — UX-grade error feedback in the chat UI: API/session/tool error messages, loading states for tool execution, retry, toast notifications (Phase 4.7)
- [ ] **REQ-streamevent-hierarchy** — Replace monolithic `StreamEvent` with discriminated union `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`; update SSE serialization + frontend parsing (Phase 4.7)
- [ ] **REQ-pydantic-validators** — `Flight.arrival > departure`, `FlightQuery.departure_date >= today`, `FlightQuery.origin != destination` — additive to the existing `validate_dates` validator (Phase 4.8)
- [ ] **REQ-test-fixture-dedup** — Shared `create_mock_flight()` factory and `parse_sse_events()` helper; refactor existing tests to consume them; delete orphaned `ToolCallCard.tsx` / `ToolResultCard.tsx` (Phase 4.8)
- [x] **REQ-pydantic-ai-migration** — Port `ChatService` from LangChain `bind_tools()` to PydanticAI agents while preserving the SSE event contract; convert `LLMProvider`/`BoundProvider` from `typing.Protocol` to `abc.ABC`; rewire `_flight_client` attribute injection to PydanticAI dependencies; remove `langchain*` from `pyproject.toml`; ADR-001 transitions Locked → Superseded (Phase 5 — *resequenced ahead of Postgres on 2026-06-02 per PR #20 review*) — Validated in Phase 5 (2026-06-03)
- [x] **REQ-p5-stream-event-abc** — Refactor `StreamEvent` discriminated-union alias into a proper `StreamEvent(ABC)` hierarchy; pulled into Phase 5 because the producer is being rewritten anyway (Phase 5) — Validated in Phase 5 (2026-06-03)
- [ ] **REQ-postgres-redis-compose** — `docker-compose.yml` brings up backend + frontend + Postgres + Redis with named volumes and a single `OLLAMA_BASE_URL` override; `psycopg` async + `sqlmodel` ORM for `User` / `Conversation` / `Message` (the `Message` shape now targets PydanticAI's `ModelMessage` directly); users seeded from PG (replaces `AUTH_USERS` env-var workaround); CORS resolved by the compose network (Phase 6)
- [ ] **REQ-real-flight-api** — Replace `MockFlightAPIClient` with a real flight provider (Amadeus) behind the existing `FlightAPIClient` ABC; outbound HTTP via **`pyreqwest`** (not `aiohttp`); reuse retry + circuit breaker + `APIError` hierarchy; gated integration tests (Phase 7)
- [ ] **REQ-security-headers** — CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy on every response; CORS allowlist from `settings.cors_origins` if not already solved by the compose network; `rehype-sanitize` with the custom Chakra-aware config (Phase 8)
- [ ] **REQ-structured-logging** — `structlog` JSON logging; `RequestLoggingMiddleware` issues a `request_id`; `ChatService` logs tool calls, streaming durations, and errors with `request_id` + `session_id` (Phase 8)
- [ ] **REQ-backend-test-coverage-60** — Reach 60% backend coverage with no-network / no-Ollama tests (Phase 8)
- [ ] **REQ-coverage-ratchet-80** — Raise CI threshold to `--cov-fail-under=80`; frontend `coverage: { branches: 70, lines: 80 }` (Phase 8)

### Out of Scope

<!-- Explicit boundaries with reasoning, to prevent re-adding. -->

- **Rate limiting (`slowapi` or otherwise)** — Dropped from v1 hardening. Demo-grade traffic does not warrant it; revisit only if the project ever gets a public deployment surface.
- **REQ-session-management refactor** / **REQ-di-lifespan-fix** — Superseded. Postgres + `app.state` lifespan singletons (Phase 6) are the durable answer; the old "introduce SessionStore ABC" / "replace `@lru_cache` with `app.state`" refactor RFCs are obsolete on either count.
- **Default-config rehype-sanitize variant** (pre-phase-4-refactor Task 10) — Superseded by the Chakra-aware custom-config variant (Phase 8 / REQ-security-headers). Default config strips Chakra table elements and silently regresses flight-result rendering.
- **Reducer-based ChatInterface decomposition** (pre-phase-4-refactor Task 5) — Superseded by the hooks-shape decomposition shipped in PR #3.
- **`openapi-typescript` codegen for frontend types** — Better long-term than hand-written `types/chat.ts`, but premature until the API contract stabilizes; revisit after Phase 6 (Postgres re-platform — the PydanticAI swap in Phase 5 keeps the SSE contract stable, but the conversation-rename in Phase 6 reshapes the REST surface).
- **Playwright frontend E2E** — Defer until Phase 4 stabilizes the component surface.
- **JWT token revocation / deny-list** — Mitigated by 60-min expiry; full DB-backed revocation is post-v1.
- **User registration endpoint** — Internal/demo project; users are seeded (env-var workaround in Phase 4.2, Postgres-seeded from Phase 6 onward).
- **Additional travel tools (hotels, restaurants, weather)** — v1 covers flights only.
- **Multi-city / multi-leg trip planning** — v1 covers single origin/destination/date queries.
- **DSPy / GraphQL migration** — Architectural pivots, not in scope. (PydanticAI is the architectural pivot v1 *does* take, in Phase 5.)

## Context

**Codebase state.** Brownfield, **non-functional in the browser as of 2026-05-15**: chat requests return 401 because no frontend login route ships, and the in-UI provider/model selector does not produce a working session. The repository has shipped Phases 1-3 plus the partial Phase 4.1 surface (UI without working wiring), plus engineering-quality PRs #1, #3, #5 (#2 and #4 shipped but partial — see Partial / Broken bucket above). Authoritative onboarding doc is `CLAUDE.md` (the legacy `README.md` references `gpt-oss20b`, `PLAN.md`, and `copilot-instructions.md` — all stale). v1 begins by unbreaking auth and the model selector (Phase 4.2).

**Two parallel phasing schemes existed pre-ingest.** The legacy product roadmap (Phase 1 Foundation → Phase 6 Production Readiness) and the engineering plan (Phase 0 Bug Fixes → Phase 6 Coverage 80%) shared phase numbers. Per user direction, **the product-phase numbering scheme is authoritative**. Engineering items now live inside the renumbered phase tree (4.2 Unbreak App → 4.8 → 5 PydanticAI → 6 Postgres+compose → 7 Real API → 8 Hardening); there is no parallel "engineering Phase N" track. *(Phase 5 ↔ 6 swap was made on 2026-06-02 per PR #20 review.)*

**Architectural philosophy.** Async-first, type-safe, dependency-injected, SOLID. Comments answer *why*, never *what*. Default `pytest` is fast and **does not call Ollama** — chat tests use a `MockLLMStream` fixture (delivered in Phase 4.4). Test roles: **unit** = pure functions / in-process logic, no external services; **integration** = FastAPI test client + (post-Phase-6) PG container + mock LLM stream + mock travel API; **E2E** = real auth login flow + real travel API only, gated on credentials.

**Named patterns** (locked through Phase 4.x; ADR-001 LangChain → Superseded in Phase 5 *(was Phase 6 before the 2026-06-02 swap)*, see `ARCHITECTURE.md` and ADRs below):
- Data Model Pattern — Pydantic models, no business logic except validators.
- Abstract Client Pattern — `BaseAPIClient (ABC) → FlightAPIClient (ABC) → MockFlightAPIClient | <RealProvider>`. Async only. Retry + circuit breaker + custom exception hierarchy. Real client uses `pyreqwest` (Phase 7).
- Functional Service Pattern — pure async functions; cross-cutting concerns via decorators.
- Dependency Injection Pattern — FastAPI `Depends()` parameters today; **target**: `Annotated[T, Depends(...)]` (lands in Phase 4.3 alongside the CI reset). Singletons live in `app.state` (lifespan-managed); never `@lru_cache`.

**Frontend** — `App.tsx` (layout + session init), `ChatInterface.tsx` (post PR #3 hooks-shape decomposition), `ToolExecutionCard.tsx`, `ThinkingCard.tsx`. Phase 4.2 adds a `Login.tsx` route + protected-route wrapper. Vite proxies `/api/*` to `localhost:8000`. `ToolCallCard.tsx` + `ToolResultCard.tsx` are candidates for deletion in Phase 4.8 — verify no remaining imports before deletion.

**Workflow.** GSD framework: `/gsd-discuss-phase`, `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-progress`. Project-local skills: `/fastapi`, `/chakra-ui`, `/pydantic-ai-agent-builder`. All ops via `just`.

**Known accepted limitations** (mitigations in place; not bugs to fix):
- No JWT token revocation — 60-min expiry, rotate `jwt_secret` on breach.
- `AUTH_USERS` env-seeded user store is a Phase 4.2 quick-and-dirty workaround; replaced by PG-seeded users in Phase 6.
- E2E tests run only when credentials are present (auth flow + real travel API). Removed from default CI; not nightly-scheduled.
- `search_flights._flight_client` monkey-patch retained — works, contained, refactor when adding more tools.

## Constraints

- **Tech stack — runtime**: Python 3.13 backend (uv), Node 22 frontend (npm). CI pins these versions; no `engines.node` field in `frontend/package.json` enforces it for local dev.
- **Tech stack — frameworks**: FastAPI ≥ 0.120, Pydantic ≥ 2.12, React ≥ 18, TypeScript ≥ 5, Chakra UI v3, Vite, react-markdown + remark-gfm. **LangChain 1.0** is the current chat agent runtime through Phase 4.x; **PydanticAI** replaces it in Phase 5 (rationale: lighter, easier to test; resequenced ahead of the PG re-platform on 2026-06-02 per PR #20 review).
- **LLM access**: v1 supports two paths, both selectable per session: (a) **dynamic Ollama model discovery** from the host (no hard-coded default; `OLLAMA_BASE_URL` configurable); (b) **cloud LLM via API key** (OpenAI, Anthropic), supplied by env var or session creation payload. Stub-only providers are not acceptable. The legacy `init_chat_model(reasoning=True)` qwen3:4b path remains available as one of many local models.
- **Async I/O only**: All I/O is `async def`. No `requests`. No sync file I/O on async paths. **Outbound HTTP uses `pyreqwest`** (not `aiohttp`/`httpx`) from Phase 7 onward; **database access uses `psycopg` async + `sqlmodel` ORM** from Phase 6 onward.
- **Type safety**: `mypy` runs in strict mode. Bare `type: ignore` is forbidden — every ignore must include an explanatory comment.
- **Package manager**: `uv` exclusively for Python — never `pip`, `poetry`, `conda`.
- **Lint/format**: `ruff` line length **100 today; target 120** (lands in Phase 4.3 alongside the CI reset); `isort` first-party prefix `app`; `ruff check` and `ruff format --check` must pass in CI.
- **Test layout**: `backend/tests/{unit,integration,e2e}` with markers `@pytest.mark.unit`, `.integration`, `.e2e`. The `slow` marker still exists in `pyproject.toml` today; it is **removed** in Phase 4.4 (REQ-mock-chat-tests) once chat tests no longer need Ollama gating. Default `pytest` does not require Ollama or network. **Unit** = pure functions / in-process logic, no external services. **Integration** = FastAPI test client + (post-Phase-6) PG container + mock LLM stream + mock travel API. **E2E** = real auth login flow + real travel API only, gated on credentials. AAA pattern with descriptive names.
- **Coverage gates**: 60% backend floor today; ratcheted to 80% in Phase 8. Frontend `coverage: { branches: 70, lines: 80 }` added in Phase 8.
- **CI** (Phase 4.3 reset): Triggers on `push` to any branch with an open PR plus `pull_request` to `master`. **No scheduled run.** Lint + unit + integration jobs must pass for merge — branch protection on `master` enforces this. The E2E job is retained but runs only when credentials secrets are present, and exercises auth flow + real travel API only (never Ollama).
- **Auth**: JWT via `pyjwt` + `pwdlib[argon2]`. `jwt_secret`, `jwt_algorithm = "HS256"`, `jwt_expire_minutes = 60`. **Phase 4.2**: a React login route hits `POST /token`; users are still seeded from `AUTH_USERS=user1:pass1,...` as a quick-and-dirty workaround. **Phase 6**: users move to a Postgres `users` table and `AUTH_USERS` is retired. Protected routes depend on `get_current_active_user`. `GET /health` is public; everything else requires auth.
- **CORS**: Today CORS is hard-coded in `api/main.py` with `allow_origins=["http://localhost:5173"]`. Phase 6's docker-compose network resolves CORS by collapsing backend + frontend onto a single origin. If any post-Phase-6 deployment splits origins, Phase 8's `settings.cors_origins` allowlist applies (wildcard `*` forbidden).
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

<!-- Locked ADRs and locked-by-implementation decisions. ADR-002 is recorded as Obsolete (never implemented + superseded by Phase 6 PG-backed history). -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **ADR-001** Use LangChain 1.0 `bind_tools()` (not `create_agent()`) | LangGraph under the hood; works with any chat model that supports function calling; simpler to mock/test; streaming works out of the box | ⚠️ **Status: Superseded by ADR-007 (2026-06-03)** — replaced by PydanticAI in **Phase 5** *(was Phase 6; resequenced 2026-06-02 per PR #20 review)*. LangChain shipped through Phase 4.x; `langchain*` + `langgraph` removed from `pyproject.toml` in Wave 4. See `.planning/adrs/ADR-001-langchain.md` for the standalone ADR with the supersession note. |
| **ADR-002** Global `_global_chat_store` for session history | Per `NOW.md`, the premise was a misunderstanding — no `_global_chat_store` ever existed; `ChatService._histories` was per-instance from the start. | ⚠️ **Obsolete** — Phase 6 moves history into Postgres anyway, so the original ADR is doubly moot. Recorded for history only. |
| **ADR-003** Stream LLM responses via Server-Sent Events using FastAPI `StreamingResponse` | Native browser support, simpler than WebSockets for unidirectional streaming, FastAPI-friendly. | ✓ Locked-as-implemented (`StreamingResponse` in `routes.py`) |
| **ADR-004** Pydantic models for all data structures (no raw dicts) | Validation, OpenAPI schema generation, mypy integration, free serialization | ✓ Good — locked |
| **ADR-005** Mock-first external API (build `MockFlightAPIClient`, real Amadeus later) | Faster iteration, deterministic tests, no API credentials during dev | ✓ Good — locked; real client lands Phase 7 (after PydanticAI + compose re-platform) |
| **ADR-006** Postgres + `psycopg` async + `sqlmodel` ORM, in docker-compose, single spin-up | Replaces in-memory `_histories` and `AUTH_USERS` env-seed; named volumes survive restart; CORS resolved by single compose network; `OLLAMA_BASE_URL` overridable. **Pre-phase spike**: verify `postgresql+psycopg://` async URI works with SQLModel async session out-of-the-box on SQLAlchemy ≥ 2.0 (SQLModel historically targeted `asyncpg`; if `psycopg` async needs adapter glue, surface that before locking the model layer). | — Pending — lands **Phase 6** *(was Phase 5; resequenced 2026-06-02 per PR #20 review)* |
| **ADR-007** PydanticAI replaces LangChain for the chat agent | Lighter footprint, easier to mock/test, native Pydantic integration; single-tier `Agent` shape collapses the Phase 4.5 `LLMProvider`/`BoundProvider` two-tier; `RunContext[Deps]` closes the `_flight_client` monkey-patch; native `<think>` tag parsing for Ollama qwen3 | ✓ **Status: Locked (2026-06-03)** — shipped in **Phase 5**. RESEARCH OQ-01..OQ-05 verified against installed `pydantic-ai 0.8.1` (HIGH confidence). See `.planning/adrs/ADR-007-pydantic-ai.md` for the standalone ADR. |
| **ADR-008** `pyreqwest` for outbound HTTP (real travel APIs) | Async-first Rust-backed client, performance + ergonomics; replaces `aiohttp` references in earlier docs | — Pending — lands Phase 7 |
| **ADR-009** Drop rate limiting from v1 hardening | Demo-grade traffic does not warrant `slowapi` + key-function complexity; revisit only if a public deployment surface materializes | ✓ Decided — applies from Phase 8 onward |
| JWT auth via `pyjwt` + `pwdlib[argon2]` (HS256, 60-min expiry) | Standard, well-supported | ✓ Backend shipped PR #4 — login UI lands Phase 4.2; users move from `AUTH_USERS` env to PG in Phase 6 *(was Phase 5 before the 2026-06-02 swap)* |
| `uv` exclusively for Python package management | Faster, lockfile-first, replaces `pip`/`poetry`/`conda` | ✓ Good — locked |
| `mypy` strict mode with annotated `type: ignore` only | Prevents silent type erosion | ✓ Good — locked |
| Lifespan-managed singletons in `app.state` (no `@lru_cache`); routes migrate to `Annotated[T, Depends(...)]` in Phase 4.3 | Proper FastAPI DI; testable without full lifespan; no module-level state; modern FastAPI idiom | Singletons ✓ shipped; Annotated DI — Pending (Phase 4.3) |
| Product-phase numbering authoritative; engineering items folded into the renumbered phase tree | Avoids parallel "Phase N" tracks | ✓ Good — applied at this synthesis |
| Hooks-shape `ChatInterface` decomposition (PR #3) over reducer-based variant | PR #3 already merged with the hooks variant; reducer variant has no remaining advantage | ✓ Good — superseded |
| Custom Chakra-aware `sanitizeConfig.ts` for `rehype-sanitize` (over default config) | Default config silently strips Chakra-rendered tables, regressing flight-result UX | — Pending — lands in Phase 8 |
| Adopt user-stated milestone goal: unbreak app → swap to PydanticAI → re-platform onto PG+compose → real travel API → hardening *(Phase 5 ↔ 6 swap on 2026-06-02 per PR #20 review)* | User's success metric: working browser demo (login → provider select → chat → real flight results), 80% backend coverage, no CRITICAL security findings | — Pending — drives v1 roadmap |

---
*2026-06-03 after Phase 5 completion — PydanticAI migration shipped:
`LLMProvider(ABC)` + `build_agent(tools, deps_type)` (single-tier;
`BoundProvider` retired); `ChatDeps` frozen dataclass; four concrete providers
reshaped against `pydantic_ai.models.*` (Ollama via `OllamaProvider`, OpenAI
with o-series → `OpenAIResponsesModel` dispatch, Anthropic via
`AnthropicProvider`, LM Studio via `OpenAIProvider` with no api-key sentinel);
`search_flights` rewritten with `ctx: RunContext[ChatDeps]` (the
`_flight_client` back-door is deleted); `ChatService.chat_stream()` rewritten
against `agent.iter()` walking `ModelRequestNode` / `CallToolsNode`;
`StreamEvent(BaseModel, ABC)` with five concrete subclasses (wire format
byte-equivalent to Phase 4.7); `ConversationStore(ABC)` +
`InMemoryConversationStore` (Phase 6 swaps in `PostgresConversationStore`);
`MockLLMStream` rewritten to drive `FunctionModel(stream_function=...)` —
default `pytest` stays fast and offline. Dependency swap: `langchain`,
`langchain-core`, `langchain-ollama`, `langchain-openai`,
`langchain-anthropic`, and `langgraph` all removed; `pydantic-ai>=0.8.1`
added; `pydantic` floor raised to `>=2.12`. **ADR-001 → Superseded by
ADR-007; ADR-007 → Locked.** Standalone ADR files now live under
`.planning/adrs/`. Phase 5 success criteria 1-6 (ROADMAP.md lines 246-251)
all met. REQ-pydantic-ai-migration + REQ-p5-stream-event-abc moved Active →
Validated.*

*2026-06-02: PR #20 review pass — ARCHITECTURE.md aligned to ADR-008 (`pyreqwest` per CLAUDE.md, replacing stale `aiohttp`/`httpx` references) and **Phase 5 ↔ Phase 6 resequenced**: PydanticAI migration now lands first, Postgres + Redis + docker-compose lands second. Rationale: the agent surface is small enough that doing PydanticAI before persistence is the cheapest moment, eliminates the `Message` shape gamble (table now targets `ModelMessage` directly), and folds three pending reworks (LangChain → PydanticAI, `LLMProvider` Protocol → ABC, `_flight_client` back-door → DI) into one change. `REQ-p5-*` IDs retain their `p5` prefix as historical schedule labels.*

*Last updated: 2026-05-18 after Phase 4.5 completion — LLM provider abstraction shipped: `LLMProvider`/`BoundProvider` Protocols, `LLMProviderFactory` with 4-way `match` dispatch, four real providers (Ollama with dynamic discovery / OpenAI / Anthropic / LM Studio), per-session provider injection, three new auth-protected endpoints (`POST /api/providers/refresh`, `POST /api/providers/{provider}/test`, `GET /api/chat/sessions`), per-user session partitioning, minimal API-key log scrubber, Sidebar + settings UI with active-model badge. REQ-llm-provider-abstraction moved Active → Validated. Verifier passed 9/9 must-haves; 5 critical code-review findings fixed inline before completion.*

*2026-05-17 after Phase 4.4 completion — MockLLM fixture (`BaseChatModel` subclass) + 4 locked tests; custom pytest markers (`unit`, `integration`, `e2e`, `slow`) removed; test selection is path-only. REQ-mock-chat-tests moved Active → Validated.*

*2026-05-15: PR #6 review pass — promoted Postgres+compose & PydanticAI into v1, dropped rate limiting, status-corrected partial Phase 4.1 / auth / CI shipments, renumbered phases through Phase 8. Follow-up adversarial review then reframed declared-as-shipped targets (ruff 120, Annotated DI, `slow` marker) as Phase 4.3/4.4 deliverables, added rework-risk + sequencing notes around Phase 4.5 ↔ 5 ↔ 6, added a `psycopg`+SQLModel pre-phase spike to ADR-006, and named acceptance fixture sources for REQ-tool-json-output.*
