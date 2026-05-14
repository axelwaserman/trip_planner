# Constraints (technical, NFR, contract)

> Synthesizer note: No source doc was classified as a SPEC. Constraints below are extracted from the architectural and operational rules embedded in `ARCHITECTURE.md`, `CLAUDE.md`, `CI_CD_WORKFLOW.md`, and the implementation plans. Each entry is typed (`api-contract` | `schema` | `nfr` | `protocol` | `tooling`).

---

## CON-async-io-first

- source: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/ARCHITECTURE.md`
- type: protocol
- statement: All I/O operations are `async def`. No `requests`, no synchronous file I/O on async paths. FastAPI + LangChain + aiohttp throughout.

---

## CON-mypy-strict

- source: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/ARCHITECTURE.md`
- type: tooling
- statement: `mypy` runs in strict mode. Bare `type: ignore` is forbidden — every ignore must include an explanatory comment. Full type hints everywhere.

---

## CON-package-manager-uv

- source: `/Users/axel/code/trip_planner/CLAUDE.md`
- type: tooling
- statement: Python package management uses `uv` exclusively — never `pip`, `poetry`, or `conda`.

---

## CON-format-lint

- source: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md`
- type: tooling
- statement: `ruff` line length is 100. `isort` first-party prefix is `app`. `ruff check` and `ruff format --check` must pass in CI.

---

## CON-test-pyramid

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (Testing Strategy)
- type: nfr
- statement: Test split target — Unit (70%), Integration (20%), E2E (10%). Aim for >80% coverage in business logic. Markers: `@pytest.mark.unit`, `.integration`, `.e2e`, `.slow`. Default test invocation excludes `slow`.

---

## CON-test-no-network-no-ollama

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 3 acceptance)
- type: nfr
- statement: Default test suite (`pytest -m "not slow"`) must not require network access, the Ollama daemon, or any external API. E2E tests that need Ollama are gated to `workflow_dispatch` or `schedule` only and excluded from PR CI.

---

## CON-test-aaa-pattern

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 3 acceptance)
- type: tooling
- statement: All new tests use the AAA (Arrange / Act / Assert) pattern with descriptive names.

---

## CON-coverage-floor-60

- source: `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md`, `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 2)
- type: nfr
- statement: Backend CI enforces `--cov-fail-under=60` initially. Phase 6 raises this to 80 (see `CON-coverage-floor-80`). The two are sequential — only one is active at any time.

---

## CON-coverage-floor-80

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 6)
- type: nfr
- statement: After Phase 6, backend CI enforces `--cov-fail-under=80`. Frontend coverage thresholds: `{ branches: 70, lines: 80 }`.

---

## CON-frontend-coverage-future

- source: `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md` (Future Additions)
- type: nfr
- statement: Frontend job will gain `npm run test:coverage` step and frontend coverage threshold enforcement after Phase 4.

---

## CON-ci-pr-gates

- source: `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md`, `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 2)
- type: protocol
- statement: Branch protection on `master` requires both `Backend (Python 3.13)` and `Frontend (Node 22)` jobs to pass. Branches must be up-to-date before merging. Bypass not permitted.

---

## CON-ci-concurrency

- source: `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md`
- type: protocol
- statement: CI uses `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` so older in-flight runs are cancelled when a new push arrives on the same ref.

---

## CON-runtime-versions

- source: `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md`, `/Users/axel/code/trip_planner/README.md`, `/Users/axel/code/trip_planner/ARCHITECTURE.md`
- type: tooling
- statement:
  - Python: 3.13
  - Node: 22 (CI) / 20+ (README minimum)
  - The README's "Node.js 20+" is a lower bound; CI pins 22, which is the operational target.

---

## CON-tech-stack-versions

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (Technology Stack)
- type: tooling
- statement:
  - FastAPI ≥ 0.120
  - LangChain ≥ 1.0 (with LangGraph)
  - Pydantic ≥ 2.12
  - React ≥ 18, TypeScript ≥ 5
  - Chakra UI v3, Vite, react-markdown + remark-gfm

---

## CON-llm-provider-current

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md`, `/Users/axel/code/trip_planner/NOW.md`, `/Users/axel/code/trip_planner/ROADMAP.md`, `/Users/axel/code/trip_planner/phases/phase-4.1-llm-provider-config.md`
- type: tooling
- statement: Default LLM is **qwen3:4b** via Ollama, accessed through `init_chat_model()` with `reasoning=True` for thinking-token support. `ARCHITECTURE.md` lists `qwen3:8b` (older note); `ROADMAP.md` Phase 3 deliverables and `NOW.md` confirm `qwen3:4b` as current. Authoritative current value: `qwen3:4b`.
- note: `README.md` references `gpt-oss20b` — that value is stale and superseded by the more recent docs (see INFO entry in conflicts report).

---

## CON-auth-jwt

- source: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 1)
- type: protocol
- statement: Auth uses JWT (`pyjwt`) with `pwdlib[argon2]` for password hashing. Protected routes depend on `get_current_active_user`. JWT settings: `jwt_secret`, `jwt_algorithm = "HS256"`, `jwt_expire_minutes = 60`. Users seeded from `AUTH_USERS=user1:pass1,...` env var. No DB. No registration endpoint. No token revocation (mitigated by 60-min expiry).

---

## CON-cors-origin-allowlist

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 5)
- type: protocol
- statement: CORS origins come from `settings.cors_origins` (default `["http://localhost:5173"]`). Wildcard `*` must never be silently allowed.

---

## CON-security-headers

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 5)
- type: protocol
- statement: All responses must include CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and Permissions-Policy headers via dedicated security middleware.

---

## CON-rate-limiting

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 5)
- type: protocol
- statement: Use `slowapi` for rate limiting with an `X-Forwarded-For`-aware key function. Per-user limits. Returns 429 over threshold. Single-process / in-memory; not horizontally scalable until a Redis backend is added.

---

## CON-markdown-sanitization

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 5), `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 10)
- type: protocol
- statement: All `<ReactMarkdown>` instances must use `rehype-sanitize`. Phase 5 prescribes a custom `sanitizeConfig.ts` preserving Chakra table elements; pre-phase-4-refactor Task 10 prescribes the default config. Phase 5 (broader scope) wins.

---

## CON-stream-event-protocol

- source: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/ARCHITECTURE.md` (ADR-003)
- type: api-contract
- statement: Server-Sent Events stream `StreamEvent` objects with `type` ∈ {`content`, `thinking`, `tool_call`, `tool_result`}. `thinking` chunks come from `chunk.additional_kwargs["reasoning_content"]`. Future state (REQ-streamevent-hierarchy) replaces single model with discriminated union including `error` event.

---

## CON-flight-tool-output-schema-current

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (LangChain Integration), `/Users/axel/code/trip_planner/CLAUDE.md`
- type: api-contract
- statement (current): `search_flights()` LangChain tool returns a JSON string with `status`, `query`, and `results` array. ARCHITECTURE.md describes this as the documented output. The pre-phase-4-refactor doc (Task 4) calls the *current* output "verbose formatted strings"; this contradiction reflects the doc being older than the actual implementation.
- statement (target — see REQ-tool-json-output): JSON object with `status`, `query`, `results[]` (each with `flight_number`, `airline`, `route`, `departure`, `arrival`, `duration_hours`, `price_usd`, `stops`), and `count`.

---

## CON-providers-api

- source: `/Users/axel/code/trip_planner/phases/phase-4.1-llm-provider-config.md`
- type: api-contract
- statement:
  - `GET /api/providers` returns available providers, their models, and credential status.
  - `POST /api/chat/session` accepts body `{"provider": "<id>", "model": "<id>"}` — both optional with sensible defaults.
  - Session metadata structure: `{ "provider": "ollama", "model": "qwen3:4b", "created_at": "<epoch>" }`

---

## CON-session-lifecycle-api

- source: `/Users/axel/code/trip_planner/NOW.md`, `/Users/axel/code/trip_planner/CLAUDE.md`
- type: api-contract
- statement:
  - `POST /api/chat/session` creates a session (returns 201).
  - `DELETE /api/chat/session/{id}` deletes a session — must remove `_histories[id]`, `_metadata[id]`, and `_last_activity[id]`.
  - Each browser tab maintains an independent session (no shared mutable state).
  - Frontend initializes session on mount (`App.tsx`).

---

## CON-no-lru-cache-singletons

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (DI Pattern), `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 9)
- type: protocol
- statement: Singletons live in `app.state` via the FastAPI `lifespan` context manager. `@lru_cache` is forbidden for singleton factories (violates DI).

---

## CON-error-hierarchy

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (Error Handling)
- type: schema
- statement:
  - `APIError` (base)
    - `APITimeoutError` (retryable)
    - `APIRateLimitError` (retryable)
    - `APIServerError` (retryable, 5xx)
    - `APIClientError` (non-retryable, 4xx)
  - `FlightSearchError` (business logic)
- Retry decorator (`app/utils/retry.py`) supports exponential backoff, circuit breaker, configurable `max_attempts`, and a `retryable_exceptions` allowlist.

---

## CON-pydantic-validators-business-rules

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 7)
- type: schema
- statement (target):
  - `Flight.arrival_time` must be > `departure_time`
  - `FlightQuery.departure_date` must be ≥ today
  - `FlightQuery.origin` must differ from `FlightQuery.destination`

---

## CON-project-layout

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (Project Structure), `/Users/axel/code/trip_planner/CLAUDE.md`
- type: tooling
- statement: Backend layout under `backend/app/`:
  - `api/main.py` (FastAPI app, lifespan)
  - `api/routes/` (chat, health, flights, auth)
  - `chat.py` (`ChatService`)
  - `config.py` (Pydantic `BaseSettings`)
  - `exceptions.py`
  - `tools/` (LangChain tools, flight client) — note: ARCHITECTURE.md draft layout shows `infrastructure/clients/` and `domain/`; CLAUDE.md describes the actual current layout as `tools/` and `models.py`. Current code (per CLAUDE.md) is the authoritative shape.
- See INFO entry in conflicts report regarding the layout difference.

---

## Constraint index

| ID | Type |
|----|------|
| CON-async-io-first | protocol |
| CON-mypy-strict | tooling |
| CON-package-manager-uv | tooling |
| CON-format-lint | tooling |
| CON-test-pyramid | nfr |
| CON-test-no-network-no-ollama | nfr |
| CON-test-aaa-pattern | tooling |
| CON-coverage-floor-60 | nfr |
| CON-coverage-floor-80 | nfr |
| CON-frontend-coverage-future | nfr |
| CON-ci-pr-gates | protocol |
| CON-ci-concurrency | protocol |
| CON-runtime-versions | tooling |
| CON-tech-stack-versions | tooling |
| CON-llm-provider-current | tooling |
| CON-auth-jwt | protocol |
| CON-cors-origin-allowlist | protocol |
| CON-security-headers | protocol |
| CON-rate-limiting | protocol |
| CON-markdown-sanitization | protocol |
| CON-stream-event-protocol | api-contract |
| CON-flight-tool-output-schema-current | api-contract |
| CON-providers-api | api-contract |
| CON-session-lifecycle-api | api-contract |
| CON-no-lru-cache-singletons | protocol |
| CON-error-hierarchy | schema |
| CON-pydantic-validators-business-rules | schema |
| CON-project-layout | tooling |
