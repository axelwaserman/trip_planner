# Requirements: Trip Planner

**Defined:** 2026-05-14
**Last revised:** 2026-05-15 after PR #6 review.
**Core Value:** A user can authenticate via a real login page, pick an LLM provider (a local Ollama model discovered from the host, or a cloud provider via API key), hold a natural conversation with the agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully.

## v1 Requirements

v1 is the **working-demo + re-platform + real-API + hardening** arc. It begins with **unbreaking the app** (a login page is missing today, and the in-UI model selector does not produce a working session), then resets CI, then mocks Ollama out of default tests, then upgrades the provider abstraction to support real cloud LLMs, then redesigns the tool JSON contract to map onto real travel-API responses, then layers errors / discriminated `StreamEvent` / Pydantic validators, then re-platforms onto Postgres + Redis + docker-compose, then migrates from LangChain to PydanticAI, then ships the real flight API, then hardens the HTTP layer (no rate limiting in v1).

The product-phase numbering scheme from the legacy `ROADMAP.md` is authoritative. Engineering items live inside the renumbered phase tree (4.2 → 4.8 → 5 → 6 → 7 → 8); there is no parallel "engineering Phase N" track.

Several requirements have already shipped on `master`. They are listed here as **Validated (shipped)** for traceability and explicitly marked `Complete (shipped)` in the traceability table so downstream tools do not re-execute them. Three earlier-shipped items are now reclassified as **Partial / Broken** because the app is not currently usable in a browser; their unfinished slices reappear in the active backlog.

### Validated (shipped pre-roadmap)

- ✓ **REQ-bug-fixes-cleanup** — Pre-Phase-4 bug fixes: `_metadata` deletion in `delete_session`, `get_session_history` raises `ValueError`, e2e import paths fixed, `langgraph` removed from deps, `pytest-cov` added (PR #1)
- ✓ **REQ-frontend-testing-refactor** — Vitest + `@testing-library/react` + `jsdom` + `@vitest/coverage-v8`; `ChatInterface.tsx` decomposed into `lib/parseSSE.ts`, `hooks/useSSEStream.ts`, `hooks/useChat.ts`; under 200 lines; unit tests for `parseSSE` and `useChat` (PR #3 — hooks-shape variant; reducer variant superseded)
- ✓ **REQ-mypy-eslint-cleanup** — mypy strict-mode fixes + ESLint cleanup (PR #5)

### Partial / Broken (shipped but unusable in the browser)

These three are reopened: backend code exists but the user-facing surface is incomplete or wrong. The unfinished slices are now Active requirements at Phase 4.2 / 4.3.

- ⚠️ **REQ-auth-backend** — JWT via `pyjwt` + `pwdlib[argon2]`, `POST /token`, protected routes via `Depends(get_current_active_user)`, `AUTH_USERS` env-seeded users (PR #4). **Backend ships; no frontend login route exists, so every `/api/*` call returns 401 in the browser.** Reopened as `REQ-login-page` (Phase 4.2).
- ⚠️ **REQ-llm-provider-ui-config** — `GET /api/providers`, `POST /api/chat/session` accepts `{provider, model}`, frontend dropdown, localStorage persistence (Phase 4.1). **UI ships but the model selector does not produce a working session — wiring is broken.** Reopened as `REQ-llm-provider-ui-fix` (Phase 4.2).
- ⚠️ **REQ-ci-cd-pipeline** — GitHub Actions CI: backend (ruff lint+format, mypy, pytest `-m "not slow" --cov=app --cov-fail-under=60`); frontend (eslint, `tsc --noEmit`); E2E gated to `workflow_dispatch`/`schedule`; branch protection on master; `concurrency` cancel-in-progress (PR #2). **Schedule fires nightly E2E with no useful signal; E2E exercises Ollama rather than auth + real travel APIs.** Reopened as `REQ-ci-reset` (Phase 4.3).

### Active

#### Phase 4.2 — Unbreak the App

- [ ] **REQ-login-page**: A React login route (`/login`) renders a Chakra UI form, calls `POST /token`, stores the resulting JWT, and redirects authenticated users to the chat. A protected-route wrapper redirects unauthenticated users back to `/login`. The current `AUTH_USERS=user1:pass1,...` env-var workaround stays in place — Postgres-seeded users are deferred to Phase 6. Logout clears the token. The chat page shows the logged-in user.
- [ ] **REQ-llm-provider-ui-fix**: Selecting a provider/model in the dropdown reliably creates a session (`POST /api/chat/session`) and the next chat turn uses that session. Failure modes (provider not configured, Ollama unreachable, cloud API key missing) surface a deterministic error message in the UI rather than a silent broken state. Acceptance: with Ollama running and one local model present, a fresh user can log in, pick a provider+model, and complete one chat turn end-to-end.

#### Phase 4.3 — CI Reset + Lint/DI Migration

- [ ] **REQ-ci-reset**: `.github/workflows/ci.yml` triggers on `pull_request` against `master` and on `push` to any branch with an open PR. **No scheduled run.** `lint` + `unit` + `integration` jobs are required for merge by branch protection. The `E2E` job is retained but runs only when relevant secrets are present, and exercises **auth login flow** + **real travel API** only — never Ollama. `concurrency: { group: <workflow>-<ref>, cancel-in-progress: true }` is added.
- [ ] **REQ-lint-line-length-120**: `ruff` line length raised from 100 to 120 in `pyproject.toml`; `ruff format` applied across the codebase; CI's `ruff format --check` continues to pass.
- [ ] **REQ-annotated-depends**: All FastAPI route dependencies migrated from bare `Depends()` to `Annotated[T, Depends(...)]` per current FastAPI idiom; mypy strict still passes; behaviour unchanged.

#### Phase 4.4 — Mock Chat in Tests

- [ ] **REQ-mock-chat-tests**: A `MockLLMStream` fixture under `backend/tests/fixtures/llm.py` produces deterministic streams of `content` / `thinking` / `tool_call` / `tool_result` chunks. All chat tests in `unit/` and `integration/` consume it; no chat test in the default suite calls a real Ollama instance. The `slow` pytest marker is removed (`pyproject.toml` `addopts` updated). The README / `CLAUDE.md` describe what unit / integration / e2e tests *contain* by purpose, not just by directory.

#### Phase 4.5 — LLM Provider Abstraction (real cloud + dynamic Ollama)

- [ ] **REQ-llm-provider-abstraction**: `LLMProvider` Protocol with `ainvoke`, `astream`, `bind_tools`, `get_provider_name`, `validate_config`. Implementations: `OllamaProvider` performs **dynamic model discovery** by hitting Ollama's `GET /api/tags` against `OLLAMA_BASE_URL` (no hard-coded model list); `OpenAIProvider` and `AnthropicProvider` are **real**, not stubs, and accept API keys from env vars or session payload. `LLMProviderFactory` builds a provider from session-scoped config. `ChatService` accepts a provider via DI rather than a bare `BaseChatModel`. `validate_config` surfaces missing API keys as clear 400 errors at session creation. Each real cloud provider has a happy-path acceptance test, gated on the corresponding API key being present in the test environment (skipped in default PR CI). **Rework risk**: the Protocol surface mirrors LangChain's `BaseChatModel`; Phase 5 (PydanticAI) is `Agent`-shaped and will retire `bind_tools` from the Protocol and convert it to an ABC at the same time. *(Resequenced 2026-06-02 — was originally Phase 6.)*

#### Phase 4.6 — Vendor-Neutral Tool JSON

- [ ] **REQ-tool-json-output**: `search_flights()` returns a structured JSON shape designed to map cleanly onto Amadeus `FlightOffer`, Skyscanner `Itinerary`, and Google Flights search responses. Required field shape: endpoints carry IATA + city + (optional) terminal; departure/arrival are ISO-8601 with timezone; multi-leg journeys live in `segments[]`; price is `{amount, currency}`; carriers carry IATA + display name; `count` and `query` echo back the request. The Pydantic models are reusable for the real Phase 7 client. `ToolExecutionCard` renders the structured result as a table for `results[]`, lists for arrays, and labelled sections for nested objects — never as a raw JSON blob. **Acceptance fixtures** (locked in the phase plan): Amadeus Flight Offers Search public sample from `developers.amadeus.com/self-service/category/flights`; Skyscanner Rapid public reference sample from `partners.skyscanner.net`; Google Flights search-response sample from a public Postman / community collection (drop the third fixture and document the omission if no representative sample exists). Each fixture must normalize into our shape without lossy field collapses, asserted by tests.

#### Phase 4.7 — Error Handling + StreamEvent Hierarchy

- [ ] **REQ-error-handling-feedback**: Frontend renders distinct, actionable error messages for API errors, session errors, and tool errors. `ToolExecutionCard` shows a loading state during tool execution. Failed tool calls offer a retry control. Toast notifications surface non-blocking errors. Errors do not silently break the streaming UI.
- [ ] **REQ-streamevent-hierarchy**: Replace the monolithic `StreamEvent` model with a discriminated union — `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent`. Update SSE serialization on the backend and `parseSSE` on the frontend. Each event type carries only its own fields. The new `ErrorEvent` is the transport for REQ-error-handling-feedback's tool-error and stream-error paths.

#### Phase 4.9 — Pre-Phase-5 Prep

- [x] **REQ-model-restructure**: `backend/app/models.py` is deleted. Domain models are split into four module files: `backend/app/auth/models.py` (User, TokenResponse), `backend/app/chat/models.py` (ChatSessionInfo, ChatHistoryMessage, SessionCreateRequest, ChatRequest, StreamEvent hierarchy), `backend/app/providers/models.py` (ProviderConfig, SessionCreateError, ProbeResult), `backend/app/flights/models.py` (FlightQuery, Flight, FlightSegment, FlightSearchResult). All intra-app imports updated; `from app.models import X` references replaced with the new module path. `mypy --strict` and `just check` pass with no new ignores.
- [x] **REQ-user-repository**: A `UserRepository` protocol is extracted (e.g., `backend/app/auth/repository.py`), declaring `get_user(username: str) -> UserInDB | None` and `verify_password(plain: str, hashed: str) -> bool`. The env-seed implementation lives in `EnvUserRepository`. `get_current_active_user` is updated to depend on `UserRepository` via `Annotated[UserRepository, Depends(...)]` rather than importing `_users_db` directly. The module-global dict in `auth.py` is replaced by the repository class. `mypy --strict` passes; existing auth tests continue to pass.
- [x] **REQ-skill-routing**: A project-local TypeScript/React skill is created at `frontend/.claude/skills/react-stack/SKILL.md` (or `.claude/skills/react-stack/SKILL.md` at repo root), covering: Vite 5 + React 19 + TypeScript, Chakra UI v3 component patterns, Vitest + React Testing Library setup, the project's hook conventions (`useChat`, `useSSEStream`, `parseSSE`), and known pitfalls. CLAUDE.md gains a skill-routing table mapping work type to skill command for `/fastapi`, `/chakra-ui`, `/dignified-python`, and `/pydantic-ai-agent-builder`.
- [ ] **REQ-frontend-bug-fixes**: Six frontend bugs resolved: (1) empty-session guard — model/provider change only creates a new session when the active session has ≥ 1 message; (2) font harmonization — Login, Chat, and Settings use the same type scale from the shared Chakra theme; (3) double-think rendering — when LLM flow is think→tool→think→reply, both thinking blocks appear in the UI; (4) settings URL error feedback — invalid base URL on a local provider in Settings renders a human-readable inline error, not silent failure; (5) LM Studio stale cache — refreshing the model list in Settings always reflects current server state, no stale cached result; (6) sidebar overflow — model name does not overflow its container when wrapping to two lines.

#### Phase 4.8 — Validators + Test Hygiene + Orphan Cleanup

- [ ] **REQ-pydantic-validators**: Add **additional** field/model validators enforcing business rules — `Flight.arrival > Flight.departure`; `FlightQuery.departure_date >= today`; `FlightQuery.origin != FlightQuery.destination`. Note: `FlightQuery` already enforces `return_date > departure_date` via `validate_dates` (`backend/app/models.py:60-72`); this requirement is additive and must not replace or duplicate that existing validator. Invalid data rejected at the model boundary with a clear 422 response.
- [ ] **REQ-test-fixture-dedup**: Extract `create_mock_flight()` into `backend/tests/fixtures/flights.py` and `parse_sse_events()` into `backend/tests/utils/sse.py`. Refactor existing tests to consume them. Delete orphaned `frontend/src/components/ToolCallCard.tsx` and `ToolResultCard.tsx` (superseded by `ToolExecutionCard`).

#### Phase 5 — PydanticAI Migration

> **Resequenced 2026-06-02 (PR #20 review):** PydanticAI now lands *before* Postgres. Rationale: agent surface is still small, so doing PydanticAI first folds three pending reworks (LangChain → PydanticAI, Protocol → ABC, `_flight_client` back-door → DI) into one change and lets Phase 6's `Message` SQLModel be shaped against PydanticAI's `ModelMessage` from the start instead of being retrofitted.

- [ ] **REQ-pydantic-ai-migration**: Replace LangChain `init_chat_model` + `bind_tools()` with PydanticAI `Agent`. The discriminated `StreamEvent` union over the SSE wire (from Phase 4.7) is preserved — **frontend must not need to change**. Inside `ChatService`, the LangChain-specific `chunk.additional_kwargs["reasoning_content"]` extraction is rewritten against PydanticAI's stream surface (this is not a verbatim port). `LLMProvider` and `BoundProvider` from Phase 4.5 are converted from `typing.Protocol` to `abc.ABC` (closing the ARCHITECTURE.md "Known Tech Debt" entry); `bind_tools` is retired from the interface. `OllamaProvider`/`OpenAIProvider`/`AnthropicProvider`/`LMStudioProvider` are reshaped around PydanticAI `Model` + `Agent`. `ChatService` orchestrates a PydanticAI `Agent` per session; tool registration moves from LangChain `@tool` to PydanticAI's tool API; the `search_flights._flight_client` attribute-injection back-door is replaced by PydanticAI's per-agent dependency mechanism. `langchain`, `langchain-core`, `langchain-ollama`, `langchain-openai`, `langchain-anthropic` are removed from `pyproject.toml`; `pydantic-ai` is added. The `MockLLMStream` fixture from Phase 4.4 is updated to drive the new agent surface. ADR-001 transitions Locked → Superseded; ADR-007 (PydanticAI) becomes Locked.

- [ ] **REQ-p5-stream-event-abc**: Refactor the `StreamEvent` discriminated-union alias into a proper `StreamEvent(ABC)` base class with `ContentEvent`, `ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`, `ErrorEvent` as concrete subclasses. The `Annotated[..., Field(discriminator="type")]` union and the per-class `type: Literal[...]` instance fields are implementation details that leak Pydantic internals into consumers — encapsulate them behind the ABC. **Pulled into Phase 5** because the producer (`ChatService.chat_stream`) is being rewritten against PydanticAI's stream surface anyway — the ABC refactor is a natural fit for the same change.

#### Phase 6 — Postgres + Redis + docker-compose

- [ ] **REQ-postgres-redis-compose**: A single `docker compose up` brings up backend + frontend + Postgres + Redis with named volumes. Restarting compose preserves data via the named volumes (acceptance test: write a row, `docker compose down`, `docker compose up`, read the row back). Backend uses **`psycopg` async driver** + **`sqlmodel`** for `User`, `Conversation`, and `Message` models — the `Message` shape targets PydanticAI's `ModelMessage` directly (no JSON-payload escape hatch needed; PydanticAI lands in Phase 5). **Pre-phase spike**: verify `postgresql+psycopg://` async URI works with SQLModel async session out-of-the-box on SQLAlchemy ≥ 2.0 — SQLModel historically targeted `asyncpg`, so adapter glue may be required. Migrations use `alembic` (or `sqlmodel`-native migration if it suffices). `ChatService._histories` is replaced by a Postgres-backed history store. **User-data migration**: existing JWTs from Phase 4.2 are invalidated at Phase 6 boot via `jwt_secret` rotation; the bootstrap script re-seeds the same usernames from the `AUTH_USERS` env var into PG with the same passwords (hashed via `pwdlib`, then env unset). Redis is wired in for ephemeral state (e.g., active-stream tracking) but not used for rate limiting (which is dropped from v1). `OLLAMA_BASE_URL` defaults to `host.docker.internal:11434` inside compose. CORS is resolved by the compose network — the previous hard-coded `allow_origins=["http://localhost:5173"]` becomes irrelevant when frontend + backend share an origin via the proxy. The `just install` and `just backend` commands document the compose path.

#### Phase 6 — Architectural Carry-Forward from Phase 4.9 Review

> The `REQ-p5-*` IDs retain their `p5` prefix as historical schedule labels (originally scheduled for the old Phase 5). They still belong to this phase; only the phase number changed.

- [ ] **REQ-p5-conversation-rename**: Rename the `session` concept throughout the codebase to `conversation` (or `chat`) and reserve `session` for user navigation sessions (browser/JWT lifetime). Define distinct data structures for account-less conversations (pre-login) and authenticated ones, plus a migration mechanism that promotes an account-less conversation to an authenticated user's history upon login — persisting the message history without data loss.

- [ ] **REQ-p5-db-seed**: Replace `EnvUserRepository` with `PostgresUserRepository` as the only user backend. Add a `SEED_DEMO_USERS=true` config flag that pre-populates Postgres with test/demo users at startup (read once from `AUTH_USERS` env, hashed via `pwdlib`, then env unset). This makes `EnvUserRepository` redundant — remove it entirely.

- [ ] **REQ-p5-session-create-request-split**: Split `SessionCreateRequest` into two models respecting SRP: `ConversationTarget(provider, model)` for identifying what to talk to, and `ProviderCredentials(base_url, api_key)` for how to reach it. The SSRF/length validators move to `ProviderCredentials`. Update all session-creation call sites.

- [ ] **REQ-p5-flight-client-di**: Replace the back-door `search_flights._flight_client = flight_client` attribute injection with a proper FastAPI `Depends(get_flight_client)` dependency. **Note**: this may already be closed by Phase 5's PydanticAI dependency rewire — confirm at plan time and either drop the requirement or scope it to the residual FastAPI route plumbing.

- [ ] **REQ-p5-provider-info-split**: Split `ProviderInfo` into `LocalProviderInfo(available, models, base_url: str)` and `CloudProviderInfo(available, models, api_key_configured: bool)` subclasses of a `ProviderInfo` base. Update the `GET /api/providers` response schema and the frontend type definitions accordingly.

#### Phase 7 — Real Flight API

- [ ] **REQ-real-flight-api**: Replace `MockFlightAPIClient` (the default in dev/test) with a real flight provider client (Duffel) behind the existing `FlightAPIClient` ABC. **Real client uses `pyreqwest`** for outbound HTTP (not `aiohttp`/`httpx`). The existing retry decorator (exponential backoff + circuit breaker) and `APIError` hierarchy (`APITimeoutError`, `APIRateLimitError`, `APIServerError`, `APIClientError`, `FlightSearchError`) are reused. The vendor-neutral JSON shape from Phase 4.6 is the canonical normalization target. Mock client remains the test default via DI override. Real-API integration tests are gated on the Duffel API token being present in the E2E job (no API key required for PR CI). Documentation describes credential setup for local + CI use. (Phase 7 was previously planned + shipped against Amadeus; that integration was removed when Amadeus closed self-service access. The vendor-agnostic plumbing — `tenacity` retry, `pybreaker` circuit breaker, `pyreqwest`, lifespan auto-fallback shape, `/health flight_provider` field — is preserved.)

#### Phase 8 — Production Hardening (slim)

- [ ] **REQ-security-headers**: Security middleware emits CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy on every response. CORS comes from `settings.cors_origins` if any deployment splits backend + frontend onto different origins (compose collapses them, so this matters only outside compose); wildcard `*` is forbidden. All `<ReactMarkdown>` instances use `rehype-sanitize` with the custom Chakra-aware `sanitizeConfig.ts` that preserves table elements; `<script>alert(1)</script>` in LLM output renders as escaped text; flight-result tables still render correctly. **No rate limiting** — `slowapi` is explicitly out of scope per ADR-009.
- [ ] **REQ-structured-logging**: `structlog`-based JSON logging configured at startup. `RequestLoggingMiddleware` generates a `request_id` per request and attaches it to the log context. `ChatService` logs tool calls, streaming durations, and errors with `request_id` and `session_id`. Logs are JSON-formatted in production.
- [ ] **REQ-backend-test-coverage-60**: New no-network / no-Ollama tests bring backend coverage to ≥ 60% as measured by `pytest --cov=app --cov-fail-under=60`. Adds `test_chat_service.py`, `test_auth.py`, `test_config.py`, `test_routes.py`. Deletes `test_chat_service_mocked_llm.py.skip`. AAA pattern with descriptive names.
- [ ] **REQ-coverage-ratchet-80**: CI threshold raised to `--cov-fail-under=80`. New tests: `test_flight_search.py` (validation branches), `test_models.py` (Pydantic validators), `test_middleware.py` (CSP, security headers). Frontend `vitest.config.ts` enforces `coverage: { branches: 70, lines: 80 }`.

## v2 Requirements

Acknowledged but deferred. Not in the active roadmap; tracked here for visibility.

### Auth & Security (post-v1)

- **AUTH2-01**: JWT token revocation / deny-list (DB-backed)
- **AUTH2-02**: User registration endpoint (replaces the bootstrap-seeded user list)

### Tooling

- **TOOL-01**: `openapi-typescript` codegen for frontend types (replace hand-written `types/chat.ts`)
- **TOOL-02**: Playwright frontend E2E suite

### Travel Features

- **TRAVEL-01**: Hotel search tool
- **TRAVEL-02**: Restaurant search tool
- **TRAVEL-03**: Weather tool
- **TRAVEL-04**: Multi-city / multi-leg trip planning

### Architecture Pivots

- **ARCH-01**: DSPy integration (PydanticAI is the v1 architectural pivot — see Phase 5)

## Out of Scope

Explicitly excluded from v1 with reasoning. Listed here so they are not silently re-added.

| Feature | Reason |
|---------|--------|
| Rate limiting (`slowapi` or otherwise) | Demo-grade traffic does not warrant it (ADR-009). Revisit only if a public deployment surface materializes. |
| Session-management refactor (`SessionStore` ABC, replace global `_global_chat_store`) | **Premise was wrong** (no global store ever existed) and is now also **superseded** by Phase 6's Postgres-backed history. |
| DI lifespan refactor (replace `@lru_cache` with `app.state`) | **Premise was wrong.** Singletons already live in `app.state`; no `@lru_cache` factories exist. |
| Default-config `rehype-sanitize` drop-in (pre-phase-4-refactor Task 10) | Superseded by the Chakra-aware custom `sanitizeConfig.ts` (Phase 8 / REQ-security-headers). |
| Reducer-based `ChatInterface` decomposition (pre-phase-4-refactor Task 5) | Superseded by the hooks-shape decomposition shipped in PR #3. |
| JWT token revocation / deny-list | Mitigated by 60-min token expiry and `jwt_secret` rotation on breach. Deferred to v2. |
| `openapi-typescript` codegen | Premature until API contract stabilizes after Phase 4.6. Deferred to v2. |
| Playwright frontend E2E | Defer until after Phase 4 component refactor stabilizes. Deferred to v2. |
| User registration endpoint | Internal/demo project; users seeded from `AUTH_USERS` env (Phase 4.2) then PG-seeded (Phase 6). Deferred to v2. |
| Redis-backed rate limiter | Rate limiting itself is dropped from v1 (ADR-009). |
| Additional travel tools (hotels, restaurants, weather) | v1 covers flights only; deferred to v2. |
| Multi-city / multi-leg trip planning | v1 covers single origin/destination/date; deferred to v2. |
| DSPy migration | Not in v1 scope (PydanticAI is the v1 architectural pivot, in Phase 5). |
| GraphQL API migration | Not in v1 scope; deferred indefinitely. |

## Traceability

Each v1 requirement maps to exactly one phase. **Validated** requirements are listed for completeness with status `Complete (shipped)` so downstream tools do not re-execute them. **Partial / Broken** requirements have their unfinished slices reopened as new requirement IDs in the Active section.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-bug-fixes-cleanup | Phase 1 (foundation, retroactive) | Complete (shipped, PR #1) |
| REQ-frontend-testing-refactor | Phase 2 (LangChain integration, retroactive) | Complete (shipped, PR #3) |
| REQ-mypy-eslint-cleanup | Phase 1 (foundation, retroactive) | Complete (shipped, PR #5) |
| REQ-auth-backend | Phase 1 (foundation, retroactive) | Partial — backend shipped (PR #4), login UI reopened as REQ-login-page |
| REQ-llm-provider-ui-config | Phase 4.1 | Partial — UI shipped, wiring reopened as REQ-llm-provider-ui-fix |
| REQ-ci-cd-pipeline | Phase 1 (foundation, retroactive) | Partial — CI shipped (PR #2), reopened as REQ-ci-reset |
| REQ-login-page | Phase 4.2 | Pending |
| REQ-llm-provider-ui-fix | Phase 4.2 | Pending |
| REQ-ci-reset | Phase 4.3 | Pending |
| REQ-lint-line-length-120 | Phase 4.3 | Pending |
| REQ-annotated-depends | Phase 4.3 | Pending |
| REQ-mock-chat-tests | Phase 4.4 | Pending |
| REQ-llm-provider-abstraction | Phase 4.5 | Pending |
| REQ-tool-json-output | Phase 4.6 | Pending |
| REQ-error-handling-feedback | Phase 4.7 | Pending |
| REQ-streamevent-hierarchy | Phase 4.7 | Pending |
| REQ-model-restructure | Phase 4.9 | Complete |
| REQ-user-repository | Phase 4.9 | Complete |
| REQ-skill-routing | Phase 4.9 | Complete |
| REQ-frontend-bug-fixes | Phase 4.9 | Pending |
| REQ-pydantic-validators | Phase 4.8 | Pending |
| REQ-test-fixture-dedup | Phase 4.8 | Pending |
| REQ-pydantic-ai-migration | Phase 5 | Pending |
| REQ-p5-stream-event-abc | Phase 5 | Pending |
| REQ-postgres-redis-compose | Phase 6 | Pending |
| REQ-p5-conversation-rename | Phase 6 | Pending |
| REQ-p5-db-seed | Phase 6 | Pending |
| REQ-p5-session-create-request-split | Phase 6 | Pending |
| REQ-p5-flight-client-di | Phase 6 | Pending |
| REQ-p5-provider-info-split | Phase 6 | Pending |
| REQ-real-flight-api | Phase 7 | Pending |
| REQ-security-headers | Phase 8 | Pending |
| REQ-structured-logging | Phase 8 | Pending |
| REQ-backend-test-coverage-60 | Phase 8 | Pending |
| REQ-coverage-ratchet-80 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 35 total (3 fully validated + 3 partial/broken + 29 active)
- Mapped to phases: 35
- Unmapped: 0 ✓

**Note on retroactive mapping for shipped requirements:** PRs #1, #2, #4 landed alongside Phase 1 product work as the foundational quality gates the project was missing; PR #3 landed alongside Phase 2-era frontend work; PR #5 was a follow-up cleanup. The phase column for shipped items records this retroactive mapping. The active roadmap begins at Phase 4.2 (Unbreak the App).

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-06-02 after PR #20 review — Phase 5 ↔ Phase 6 swapped: PydanticAI migration (REQ-pydantic-ai-migration, REQ-p5-stream-event-abc) now lands at Phase 5, before Postgres+compose at Phase 6. The `REQ-p5-*` IDs keep their `p5` prefix as historical schedule labels.*
*Earlier: 2026-05-15 after PR #6 review (and follow-up adversarial pass) — v1 expanded to include Postgres+compose, PydanticAI migration, and a vendor-neutral tool JSON contract (Phase 4.6); rate limiting dropped; `aiohttp` → `pyreqwest`; `slow` marker scheduled for removal in Phase 4.4; ruff line length 100→120 and Annotated DI migration scheduled for Phase 4.3.*
