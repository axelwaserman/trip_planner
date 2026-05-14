# Context (running notes from DOC-typed sources)

> Synthesizer note: All 9 ingested docs were classified as `DOC`. The most decision/requirement-bearing material was extracted into `decisions.md`, `requirements.md`, and `constraints.md`. This file captures the residual narrative context — project status, philosophy, named patterns, workflow conventions — that downstream consumers (PROJECT.md, CONTEXT.md authoring) should be aware of.
>
> Source ordering below follows recency where known: most recent first.

---

## Topic: Project identity and purpose

- source: `/Users/axel/code/trip_planner/README.md`
- "AI-powered trip planning assistant with conversational interface and real-time travel data integration."
- Stated as a learning project; `copilot-instructions.md` is the historical guidance file (now superseded by `CLAUDE.md`).
- README's Tech Stack and Quick Start sections are partially stale (`gpt-oss20b` model reference, references to a non-existent `PLAN.md` in repo root). Treat README as introductory only; authoritative ops detail lives in `CLAUDE.md` and `ARCHITECTURE.md`.

---

## Topic: Current development status

- source: `/Users/axel/code/trip_planner/NOW.md` (2025-11-14), `/Users/axel/code/trip_planner/ROADMAP.md` (2025-11-14)
- Both docs report Phase 3 (Mock Flight Search Tool) **complete**. `qwen3:4b` model with reasoning mode in use. 56/76 tests passing (20 E2E skipped).
- `NOW.md` states the next focus is Phase 4 — LLM Provider Flexibility & UI Polish — and lists a reassessed priority order (LLM provider UI, structured tool output, error feedback, then frontend state mgmt and testing polish).
- `phase-4.1-llm-provider-config.md` (2025-11-14) reports Phase 4.1 (the LLM provider UI sub-phase) **complete**. Next sub-phase pointer is **Phase 4.2: Structured Tool Output**.
- Recent git commits (post the doc dates) show additional progress: Phase 0 bug-fix PR #1 merged, CI added in PR #2, frontend Vitest decomp in PR #3, JWT auth in PR #4, mypy fixes in PR #5. These map roughly to phases described in `IMPLEMENTATION_PLAN.md` but with parallel/independent numbering vs the `ROADMAP.md` Phase 1–6 product scheme.

---

## Topic: Two parallel phasing schemes

- sources: `/Users/axel/code/trip_planner/ROADMAP.md`, `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md`
- `ROADMAP.md` uses **product phases**: Phase 1 (Foundation/FastAPI), Phase 2 (LangChain), Phase 3 (Mock Flight Tool), Phase 4 (Provider Flexibility), Phase 5 (Real API), Phase 6 (Production Readiness).
- `IMPLEMENTATION_PLAN.md` (dated 2026-05-13) uses **engineering phases** focused on cleanup and quality gates: Phase 0 (Bug Fixes), Phase 1 (Auth), Phase 2 (CI/CD), Phase 3 (Backend Coverage), Phase 4 (Frontend Testing), Phase 5 (Security), Phase 6 (Coverage 80%).
- These are not contradictory in scope — they describe parallel tracks — but they share Phase numbers, which is confusing. Roadmapper should disambiguate or unify the phasing.

---

## Topic: Architectural philosophy

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md` (Core Design Principles)
- Async-first, type-safe, dependency-injected, SOLID-aligned. Test split target: unit 70% / integration 20% / E2E 10%.
- Comments philosophy: never comment what — only why. Explanatory comments reserved for non-obvious business logic, performance optimizations, library workarounds, security considerations.

---

## Topic: Named patterns

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md`, `/Users/axel/code/trip_planner/CLAUDE.md`
- **Data Model Pattern** — Pydantic models in `models.py`; no business logic except validators.
- **Abstract Client Pattern** — `BaseAPIClient (ABC) → FlightAPIClient (ABC) → MockFlightAPIClient | AmadeusFlightAPIClient`. All methods async. Retry + circuit breaker. Custom exceptions.
- **Functional Service Pattern** — pure async functions; cross-cutting concerns via decorators (retry, logging); no class state.
- **Dependency Injection Pattern** — FastAPI `Depends()`; singletons via `app.state` (lifespan-managed); never `@lru_cache`.

---

## Topic: LangChain integration

- source: `/Users/axel/code/trip_planner/ARCHITECTURE.md`, `/Users/axel/code/trip_planner/CLAUDE.md`
- LangChain 1.0.3 with LangGraph under the hood.
- Use `bind_tools()` (not `create_agent()` — explicitly rejected).
- Streaming: `async for chunk in llm_with_tools.astream(messages)`.
- Provider switching is a goal (Phase 4 Provider Flexibility) — Ollama / OpenAI / Anthropic.

---

## Topic: Frontend structure

- sources: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/ARCHITECTURE.md`
- `App.tsx` — top-level layout, session init.
- `components/ChatInterface.tsx` — SSE client, message state, streaming loop. Originally 452 lines; decomposed in PR #3 (Phase 4 Frontend Testing).
- `components/ToolExecutionCard.tsx` — tool call + result with expandable details (replaces older `ToolCallCard.tsx` + `ToolResultCard.tsx`, which are now orphaned and slated for deletion).
- `components/ThinkingCard.tsx` — LLM reasoning tokens.
- Vite proxies `/api/*` to `localhost:8000` (`vite.config.ts`).

---

## Topic: Test layout and markers

- source: `/Users/axel/code/trip_planner/CLAUDE.md`, `/Users/axel/code/trip_planner/ARCHITECTURE.md`
- `backend/tests/{unit,integration,e2e}` with markers `@pytest.mark.unit`, `.integration`, `.e2e`, `.slow`.
- Default `pytest` excludes `slow` (configured via `addopts` in `pyproject.toml`).
- E2E hits real Ollama and runs ~13+ minutes; not in PR CI; gated by `workflow_dispatch` / `schedule`.

---

## Topic: Just-based command runner

- source: `/Users/axel/code/trip_planner/CLAUDE.md`
- All common operations exposed via `just`: `install`, `backend`, `frontend`, `test*`, `check`, `fix`, `build`.
- Run from repo root.

---

## Topic: GSD framework usage

- source: `/Users/axel/code/trip_planner/CLAUDE.md`
- Standard GSD commands in use: `/gsd-discuss-phase`, `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-progress`.
- Tech-specific skills: `/fastapi`, `/chakra-ui`, `/pydantic-ai-agent-builder`.
- Per-phase skill mapping is given in `IMPLEMENTATION_PLAN.md` Skills Reference table.

---

## Topic: Deferred items

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Deferred Items)
- Per-session LLM factory (provider switching) — partially fulfilled by Phase 4.1.
- Database persistence — defer until session persistence across restarts is needed.
- Docker / docker-compose — after CI green + auth stable; must override `OLLAMA_BASE_URL`.
- `openapi-typescript` codegen — premature until API stabilizes.
- Playwright frontend E2E — after Phase 4 component refactor stabilizes.
- Delete orphaned `ToolCallCard.tsx` / `ToolResultCard.tsx` after Phase 4 dedup confirms.

---

## Topic: Known accepted limitations

- source: `/Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md` (Known Limitations)
- No JWT token revocation (mitigated by 60-min expiry; rotate `jwt_secret` on breach).
- In-memory sessions lost on restart (acceptable for MVP).
- Rate limiter resets on restart (single-process); Redis backend deferred.
- E2E tests require Ollama and are not in PR CI.
- Auth users from env vars only (acceptable for internal/demo).
- `search_flights._flight_client` monkey-patch retained — works, contained, refactor when adding more tools.

---

## Topic: Pre-Phase 4 refactor — historical context

- source: `/Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md`
- Document was authored before the team realised that several of its premises were already addressed by existing code (notably session management and DI).
- Status per `NOW.md`: Tasks 1 (sessions) and 9 (DI) **N/A** — already done correctly.
- Tasks 2–8 + 10 remain valid backlog items. Roadmapper should treat this doc as a backlog source, not as a single executable phase.
- The doc itself contains a closing instruction: "Delete this file after completion - move completed work summary to ROADMAP.md." This has not happened.

---

## Topic: Cross-reference graph notes

- `NOW.md` ↔ `ROADMAP.md` form a navigational cycle (each lists the other under "see also" / "current focus" pointers). This is not a synthesis-blocking content cycle, but it is recorded as a BLOCKER per the synthesizer rules — see `INGEST-CONFLICTS.md`. Resolution is trivial: drop one of the two cross-refs in the manifest, or accept the cycle as benign documentation.
- `pre-phase-4-refactor.md` references `../NOW.md` and `ROADMAP.md` (one-way, not cyclic).
- `README.md` references `./PLAN.md` and `./copilot-instructions.md` — both are missing from the current repo. Recorded as INFO.
- `CI_CD_WORKFLOW.md` references `.github/workflows/ci.yml` — present in repo (created by PR #2).
