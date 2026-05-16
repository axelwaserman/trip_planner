# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The project uses `just` as a command runner. Run from the repo root.

```bash
just install          # Install all backend + frontend dependencies
just backend          # Start backend dev server (localhost:8000)
just frontend         # Start frontend dev server (localhost:5173)
just test             # Backend tests (unit + integration + e2e via path discovery)
just test-unit        # Unit tests only
just test-integration # Integration tests only
just test-e2e         # E2E tests with real LLM (slow, ~13+ min)
just check            # lint + format-check + typecheck (run before committing)
just fix              # Auto-fix lint + format issues
just build            # Production frontend build
```

Run a single backend test:
```bash
cd backend && uv run pytest tests/unit/test_foo.py::test_bar -v
```

Frontend tests use Vitest:
```bash
cd frontend && npm test
cd frontend && npm run test:coverage
```

**Package management**: use `uv` exclusively — never `pip`, `poetry`, or `conda`.

## Architecture

### Request Flow

```
Browser → Vite dev proxy (/api/*) → FastAPI (port 8000)
                                        ↓
                                   ChatService
                                        ↓
                            LangChain bind_tools() + LLM
                                        ↓
                              SSE stream back to browser
```

### Backend (`backend/app/`)

**Entry point**: `api/main.py` — creates the FastAPI app, configures CORS, wires the `lifespan` context.

**Lifespan** (`api/main.py::lifespan`) initialises all singletons at startup:
- `MockFlightAPIClient` (injected into the `search_flights` tool via `search_flights._flight_client`)
- LLM via `init_chat_model()` with `reasoning=True` for qwen3 thinking tokens
- `ChatService` stored in `app.state.chat_service`

The `get_chat_service` dependency is overridden to pull from `app.state`, keeping routes testable without the full lifespan.

**ChatService** (`chat.py`) owns all session state. Sessions are plain `InMemoryChatMessageHistory` objects in a `_histories: dict[str, ...]`. There is no global store. `chat_stream()` drives the full tool-calling loop: stream LLM → detect `tool_calls` on `AIMessage` chunks → invoke tool → stream final response.

**Tools** (`tools/flight_search.py`) — LangChain tool definitions using the `@tool` decorator. The `search_flights` tool gets its client injected at startup via `search_flights._flight_client`.

**SSE streaming**: responses are streamed as `StreamEvent` objects with `type` values: `content`, `thinking`, `tool_call`, `tool_result`. `thinking` chunks come from `chunk.additional_kwargs["reasoning_content"]`.

**Named patterns** (see `ARCHITECTURE.md` for examples):
- *Data Model Pattern*: Pydantic models in `models.py`; no business logic except validators
- *Abstract Client Pattern*: `BaseAPIClient → FlightAPIClient → MockFlightAPIClient` in `tools/flight_client.py`
- *Functional Service Pattern*: stateless logic as pure `async def` functions
- *Dependency Injection Pattern*: FastAPI `Depends()` for routes; singletons via `app.state`

**LangChain**: uses `bind_tools()` (LangChain 1.0 style), not the older `create_agent()`. Switch LLM providers by passing a different `BaseChatModel` to `ChatService`.

### Frontend (`frontend/src/`)

- `App.tsx` — top-level layout and session init
- `components/ChatInterface.tsx` — SSE client, message state, streaming loop
- `components/ToolExecutionCard.tsx` — renders tool call + result with expandable details
- `components/ThinkingCard.tsx` — renders LLM reasoning tokens
- Vite proxies `/api/*` to `localhost:8000` (configured in `vite.config.ts`)

### Test structure

Tests live in `backend/tests/{unit,integration,e2e}`. Markers: `@pytest.mark.unit`, `.integration`, `.e2e`, `.slow`. Phase 04.3 dropped the `addopts` filter; `just test` now runs everything under `tests/` (unit + integration + e2e) via path discovery. Tests marked `@pytest.mark.slow` will run by default — opt out explicitly with `pytest -m "not slow"` if needed. `tests/e2e/` is currently a symbolic CI gate — the `E2E` workflow job runs on every push/PR but only collects a no-op placeholder. Real backend-over-HTTP E2E tests (auth flow, optional travel-API tests gated on a CI secret) land in later phases. See `backend/tests/e2e/README.md` for the policy.

## Key constraints

- `mypy` runs in strict mode — no bare `type: ignore` without a comment explaining why
- All I/O must be `async def`; no `requests`, no sync file I/O in async paths
- `ruff` line length is 120; `isort` first-party prefix is `app`
- Auth uses JWT (`pyjwt`) with `pwdlib[argon2]` for password hashing (`api/routes/auth.py`); protected routes depend on `get_current_active_user`
- **Cross-module taxonomies use `StrEnum`, not duplicated `Literal[...]` unions.** When the same set of stable string codes appears in more than one file (e.g. a wire-level error code shared between a service and a Pydantic response model), define it once as a `StrEnum` and import it. See `app.services.provider_probe.ProbeErrorCode` for the canonical example.
- **Tunable thresholds live on `Settings`, not as module-level constants.** Probe timeouts, retry counts, expiry windows, and similar knobs go in `app/config.py` so they can be overridden per environment via env vars. Module constants are reserved for values that are part of the contract (e.g. JSON keys, MIME types).

## Context files

- `NOW.md` — current task focus; read first when resuming work
- `ROADMAP.md` — phase status overview
- `ARCHITECTURE.md` — detailed named patterns, ADRs, and integration guides
- `phases/*.md` — per-phase task breakdowns (active phases only)

## Workflow and skills

Use the **GSD framework** for all structured development work in this repo. Key commands:

- `/gsd-discuss-phase` — explore and clarify a phase before planning
- `/gsd-plan-phase` — generate an executable plan for a phase
- `/gsd-execute-phase` — implement a planned phase with atomic commits
- `/gsd-verify-work` — verify phase goal achievement against the plan
- `/gsd-progress` — check current phase status

Use these **tech-specific skills** when working in the relevant stack:

- `/fastapi` — FastAPI, Pydantic v2, SQLAlchemy async, uv patterns; use whenever adding endpoints, fixing 422 errors, configuring CORS, or touching auth/DI
- `/chakra-ui` — Chakra UI v3 components, theming, slot recipes; use whenever editing frontend components that use `@chakra-ui/react`
- `/pydantic-ai-agent-builder` — multi-agent AI systems and orchestration; use if the LangChain layer is being redesigned or extended
