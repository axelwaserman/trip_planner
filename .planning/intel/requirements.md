# Requirements (extracted from planning docs)

> Synthesizer note: No source doc was classified as a PRD. Requirements below are derived from acceptance-criteria-bearing sections of `IMPLEMENTATION_PLAN.md`, `pre-phase-4-refactor.md`, `phase-4.1-llm-provider-config.md`, `NOW.md`, and `ROADMAP.md`. Each requirement gets a derived `REQ-{slug}` ID. Status (TODO / IN PROGRESS / COMPLETE) is preserved from the source.
>
> Where two source docs describe overlapping work with **different acceptance criteria** (e.g. Phase 4 in `ROADMAP.md` vs `IMPLEMENTATION_PLAN.md`), variants are flagged in `INGEST-CONFLICTS.md` under WARNINGS.

---

## REQ-bug-fixes-cleanup

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 0)
- scope: bug fixes, dead code removal, dependency cleanup
- status: **MERGED** (PR #1)
- description: Eliminate known bugs and dead code before feature work.
- acceptance:
  - `uv run pytest -m "not slow"` passes
  - `uv run ruff check . && uv run ruff format --check .` passes
  - `uv run mypy app/` passes
  - `delete_session` route removes `_metadata[session_id]`
  - `get_session_history("nonexistent")` raises `ValueError`
  - `langgraph` absent from `uv.lock` after `uv sync`

---

## REQ-auth-hardening

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 1); referenced by `CLAUDE.md` (JWT key constraint)
- scope: real JWT auth, protected routes
- status: **TODO** in IMPLEMENTATION_PLAN; recent git history (commit `83ce919`, PR #4) shows `feat(auth): implement JWT auth with pwdlib password hashing` already merged — status likely **DONE**, source plan has not been updated
- description: Replace placeholder auth with real JWT (`pyjwt` + `pwdlib[argon2]`); apply to all protected routes; in-memory user store seeded from `AUTH_USERS` env var.
- acceptance:
  - `POST /token` with valid credentials returns `{"access_token": "...", "token_type": "bearer"}`
  - `POST /api/chat` without Bearer token → 401
  - `POST /api/chat` with valid token → succeeds
  - `GET /api/providers` requires auth
  - `GET /health` does NOT require auth
  - Startup warns if `jwt_secret` is default value
  - All tests updated with auth headers and pass
- known limitation: No token revocation (no DB deny-list); short JWT expiry (60 min) used as mitigation.

---

## REQ-ci-cd-pipeline

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 2); detailed YAML in `/Users/axel/code/trip_planner/.planning/CI_CD_WORKFLOW.md`
- scope: GitHub Actions CI for backend + frontend; gated E2E
- status: **DONE** per git history (commit `7a5166c`, PR #2 `feat(ci): add GitHub Actions CI pipeline`); IMPLEMENTATION_PLAN still lists as TODO
- description: Automated quality gates on every push/PR.
- acceptance:
  - Push to any branch triggers CI
  - PR to `master` blocks merge if backend or frontend job fails
  - E2E never runs on PR (only `workflow_dispatch` or `schedule`)
  - Backend job: ruff lint, ruff format check, mypy, pytest `-m "not slow" --cov=app --cov-fail-under=60`
  - Frontend job: eslint, `tsc --noEmit --project tsconfig.app.json`
  - Branch protection on `master` requires `Backend (Python 3.13)` and `Frontend (Node 22)` jobs

---

## REQ-backend-test-coverage-60

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 3)
- scope: backend coverage to 60% with tests that work without Ollama
- status: **TODO (blocks on Phase 1)**
- description: Reach 60% backend coverage with tests that work without Ollama.
- acceptance:
  - `uv run pytest --cov=app --cov-fail-under=60 -m "not slow"` passes
  - No test requires network access or Ollama
  - All tests use AAA pattern with descriptive names
  - New unit/integration tests added: `test_chat_service.py`, `test_auth.py`, `test_config.py`, `test_routes.py`
  - `test_chat_service_mocked_llm.py.skip` deleted

---

## REQ-frontend-testing-refactor

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 4) **and** `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 5)
- scope: Vitest setup, decompose `ChatInterface.tsx`, hook tests
- status: **DONE** per git history (commit `d397030`, PR #3 `feat(frontend): add Vitest testing + decompose ChatInterface.tsx`)
- description: Install Vitest, decompose `ChatInterface.tsx` (originally 452 lines), add unit tests for parseSSE/useChat.
- acceptance (from IMPLEMENTATION_PLAN.md):
  - `npm test` runs Vitest
  - `parseSSE` has 100% branch coverage
  - `useChat` hook tested with mocked fetch
  - `ChatInterface.tsx` under 200 lines
  - `npm run lint && npx tsc --noEmit --project tsconfig.app.json` still passes
- variant acceptance (from pre-phase-4-refactor.md Task 5 — `useReducer` flavour):
  - Declarative state updates via `chatReducer` and `ChatAction` discriminated union
  - Streaming logic extracted into `useChatStream` custom hook
  - Imperative index tracking removed
  - Unit tests for reducer

> The two sources prescribe different decomposition strategies (custom hooks vs reducer-based). Surfaced as competing-variants in conflicts report.

---

## REQ-security-hardening

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 5); `pre-phase-4-refactor.md` Task 10 (markdown XSS subset)
- scope: CSP headers, safe CORS, rate limiting, sanitized markdown rendering
- status: **TODO (blocks on Phase 1)**
- description: CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy headers; CORS from env; slowapi rate limiting; rehype-sanitize for markdown.
- acceptance:
  - Response headers include CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
  - CORS rejects unlisted origins (no silent `*`)
  - Rate limiter returns 429 after threshold; uses `X-Forwarded-For` when present
  - Markdown tables still render correctly with sanitization on
  - `<script>alert(1)</script>` in LLM output renders as escaped text

---

## REQ-coverage-ratchet-80

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Phase 6)
- scope: raise CI coverage threshold from 60% → 80%
- status: **TODO (blocks on Phase 3 + Phase 4)**
- description: Raise CI threshold from 60% to 80% with new tests for tool, models, middleware.
- acceptance:
  - CI `--cov-fail-under=80` passes
  - New tests: `test_flight_search.py` (validation branches), `test_models.py` (validators), `test_middleware.py` (CSP, rate limit)
  - Frontend coverage threshold: `{ branches: 70, lines: 80 }`

---

## REQ-session-management

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 1) — original premise
- scope: per-session conversation history, multi-tab support
- status: **DONE / N/A** per `NOW.md` (2025-11-14): "Session management already exists (ChatService stores sessions in `_histories`). No global `_global_chat_store` exists - was a misunderstanding."
- description (original): Replace global `_global_chat_store` with `ChatSession` domain model + `SessionStore` ABC + `InMemorySessionStore`.
- acceptance (original):
  - Each browser tab creates independent session
  - No global mutable state
  - All tests passing
- resolution: Task scope was based on a false premise. `ChatService._histories` already provided per-instance session storage. Roadmapper should NOT re-create this work.

---

## REQ-llm-provider-abstraction

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 2)
- scope: `LLMProvider` Protocol + `OllamaProvider` + `LLMProviderFactory`
- status: **NOT STARTED** in the original task; partly delivered by Phase 4.1
- description: Decouple `ChatService` from a hardcoded Ollama provider via a `LLMProvider` Protocol with `ainvoke`, `astream`, `bind_tools`, `get_provider_name`, `validate_config`. Factory builds provider from session-scoped config. Future providers: OpenAI, Anthropic, Google.
- acceptance:
  - ChatService works with any provider via dependency injection
  - Provider validation checks for required config
  - Session-scoped provider selection
- partially fulfilled by REQ-llm-provider-ui-config below.

---

## REQ-llm-provider-ui-config

- source: `/Users/axel/code/trip_planner/phases/phase-4.1-llm-provider-config.md`
- scope: UI provider/model selection, persistence, session-scoped config
- status: **COMPLETE** (2025-11-14)
- description: Users can select an LLM provider (Ollama/OpenAI/Anthropic) and model from the UI. Provider selection persists in localStorage. Selecting a new provider creates a new session.
- acceptance:
  - Users can select provider from UI
  - Users can select model for chosen provider
  - Session uses selected provider/model
  - Config supports multiple API keys
  - Provider selection persists across page reloads
  - All existing tests pass
  - Works with Ollama (tested); OpenAI/Anthropic require API keys to be supplied
- API additions:
  - `GET /api/providers` returns providers + models + credential status
  - `POST /api/chat/session` accepts `{"provider": "...", "model": "..."}`
- session metadata: `{ "provider": "ollama", "model": "qwen3:4b", "created_at": "<epoch>" }`

---

## REQ-streamevent-hierarchy

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 3)
- scope: split monolithic `StreamEvent` into discriminated union of event types
- status: **NOT STARTED**
- description: Replace single `StreamEvent` model with `ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent` discriminated union; update SSE serialization and frontend parsing.
- acceptance:
  - Each event type has single responsibility
  - Type-safe discriminated union
  - Easier to add new event types

---

## REQ-tool-json-output

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 4) **and** `/Users/axel/code/trip_planner/NOW.md` (Phase 4 priority 2) **and** `/Users/axel/code/trip_planner/ROADMAP.md` (Phase 4 high priority 2)
- scope: tool returns structured JSON instead of preformatted string; UI renders tables/lists
- status: **NOT STARTED** (named as Phase 4.2 in `phase-4.1-llm-provider-config.md` next-phase pointer)
- description: `search_flights()` returns JSON with `status`, `query`, `results[]`, `count` instead of formatted strings. UI `ToolResultCard` renders tables/lists/nested objects.
- acceptance:
  - Tool returns structured JSON (shape documented in pre-phase-4-refactor.md Task 4)
  - LLM can naturally format results
  - `ToolResultCard` renders structured data (tables, lists, nested objects)
  - Tests validate JSON structure

---

## REQ-error-handling-feedback

- source: `/Users/axel/code/trip_planner/NOW.md` (Phase 4 priority 3); `/Users/axel/code/trip_planner/ROADMAP.md` (Phase 4 high priority 3)
- scope: UX-grade error feedback in frontend
- status: **NOT STARTED**
- description: Better error messages in UI for API errors, session errors, tool errors. Loading states for tool execution. Retry mechanism for failed tool calls. Toast notifications for errors.
- acceptance: not formally specified; treat as design-level requirement to be refined in plan-phase.

---

## REQ-structured-logging

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 6) and `NOW.md` (low priority 6)
- scope: per-request correlation IDs, structured JSON logging
- status: **NOT STARTED**
- description: Add `structlog`. `RequestLoggingMiddleware` generates `request_id` per request. `ChatService` logs tool calls, streaming durations, errors with full context.
- acceptance:
  - All logs have `request_id`
  - Easy to trace requests end-to-end
  - JSON-formatted logs for production

---

## REQ-pydantic-validators

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 7)
- scope: `Flight` and `FlightQuery` field/model validators
- status: **NOT STARTED**
- description: Add validators enforcing arrival > departure for `Flight`, future-date and origin ≠ destination for `FlightQuery`.
- acceptance:
  - Invalid data rejected at model level
  - Clear error messages

---

## REQ-test-fixture-dedup

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 8)
- scope: shared `create_mock_flight()` factory and `parse_sse_events()` helper
- status: **NOT STARTED**
- description: Extract `create_mock_flight()` to `tests/fixtures/flights.py` and `parse_sse_events()` to `tests/utils/sse.py`. Refactor existing tests to consume them.
- acceptance:
  - No duplicate factory code
  - Existing tests pass after refactor

---

## REQ-di-lifespan-fix

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 9); contradicted by `NOW.md` (says no fix needed)
- scope: replace `@lru_cache` singletons with FastAPI `lifespan` + `app.state`
- status: **N/A** per `NOW.md` (2025-11-14): "Dependency injection fixes (no issues found)"
- description: Use `lifespan()` context manager to instantiate singletons in `app.state`; dependency factories read from `request.app.state`.
- acceptance: proper singleton lifecycle; follows FastAPI best practices.
- resolution: `CLAUDE.md` confirms current behaviour already matches this pattern (lifespan managed singletons in `app.state`). Roadmapper should NOT re-do this.

---

## REQ-markdown-xss-sanitization

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md` (Task 10); also covered by REQ-security-hardening
- scope: `rehype-sanitize` for `ReactMarkdown`
- status: **NOT STARTED**
- description: Add `rehypeSanitize` plugin to all `<ReactMarkdown>` invocations.
- acceptance:
  - Malicious HTML stripped from markdown
  - `<script>alert(1)</script>` renders as escaped text
- note: overlaps with REQ-security-hardening Phase 5; the broader Phase 5 work also includes a custom `sanitizeConfig.ts` preserving Chakra table elements — that shape supersedes the simpler default config.

---

## Requirement IDs (index)

| ID | Status | Source(s) |
|----|--------|-----------|
| REQ-bug-fixes-cleanup | MERGED (PR#1) | IMPLEMENTATION_PLAN |
| REQ-auth-hardening | DONE (PR#4) per git; plan still TODO | IMPLEMENTATION_PLAN, CLAUDE |
| REQ-ci-cd-pipeline | DONE (PR#2) per git; plan still TODO | IMPLEMENTATION_PLAN, CI_CD_WORKFLOW |
| REQ-backend-test-coverage-60 | TODO | IMPLEMENTATION_PLAN |
| REQ-frontend-testing-refactor | DONE (PR#3) per git | IMPLEMENTATION_PLAN, pre-phase-4-refactor |
| REQ-security-hardening | TODO | IMPLEMENTATION_PLAN, pre-phase-4-refactor |
| REQ-coverage-ratchet-80 | TODO | IMPLEMENTATION_PLAN |
| REQ-session-management | DONE/N/A | pre-phase-4-refactor (superseded by NOW) |
| REQ-llm-provider-abstraction | PARTIAL | pre-phase-4-refactor |
| REQ-llm-provider-ui-config | COMPLETE | phase-4.1-llm-provider-config |
| REQ-streamevent-hierarchy | NOT STARTED | pre-phase-4-refactor |
| REQ-tool-json-output | NOT STARTED | pre-phase-4-refactor, NOW, ROADMAP |
| REQ-error-handling-feedback | NOT STARTED | NOW, ROADMAP |
| REQ-structured-logging | NOT STARTED | pre-phase-4-refactor, NOW |
| REQ-pydantic-validators | NOT STARTED | pre-phase-4-refactor |
| REQ-test-fixture-dedup | NOT STARTED | pre-phase-4-refactor |
| REQ-di-lifespan-fix | N/A | pre-phase-4-refactor (superseded by NOW) |
| REQ-markdown-xss-sanitization | NOT STARTED | pre-phase-4-refactor (subsumed by REQ-security-hardening) |
