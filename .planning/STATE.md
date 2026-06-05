---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Re-platform
status: executing
stopped_at: Phase 7 context gathered
last_updated: "2026-06-05T08:28:45.937Z"
last_activity: 2026-06-05 -- Phase 07 planning complete
progress:
  total_phases: 16
  completed_phases: 7
  total_plans: 46
  completed_plans: 45
  percent: 44
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-15)

**Core value:** A user can authenticate via a real login page, pick an LLM provider (a local Ollama model discovered from the host, or a cloud provider via API key), hold a natural conversation with the agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully.
**Current focus:** Phase 07 — real-flight-api

## Current Position

Phase: 07 (real-flight-api) — EXECUTING
Plan: 1 of 6
Status: Ready to execute
Last activity: 2026-06-05 -- Phase 07 planning complete

Progress: [███████░░░] 69% (11/16 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed: retroactive (PRs #1, #3, #5 + Phase 4.1 partial) — pre-GSD-tracking, no per-plan durations recorded
- Average duration: n/a
- Total execution time: n/a

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation & FastAPI Setup | retro (partial) | shipped 2025-11-06 → 2025-11-08 | n/a |
| 2. LangChain Integration & Chat Agent | retro | shipped 2025-11-08 → 2025-11-10 | n/a |
| 3. Mock Flight Search Tool | retro | shipped 2025-11-10 → 2025-11-14 | n/a |
| 4.1. LLM Provider UI Config | retro (partial) | shipped 2026-05-13 (wiring broken) | n/a |
| 04.3 | 7 | - | - |
| 04.4 | 2 | - | - |
| 04.5 | 13 | - | - |
| 04.6 | 2 | - | - |
| 06 | 7 | - | - |

**Recent Trend:**

- Last 5 plans: not tracked (pre-GSD)
- Trend: n/a — first GSD-tracked phase is 4.2

*Updated after each plan completion.*
| Phase 04.9 P02 | 20m | 2 tasks | 12 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- **2026-06-02 (PR #20 review): Resequence Phase 5 ↔ Phase 6 — PydanticAI migration now lands first (Phase 5), Postgres + Redis + docker-compose lands second (Phase 6).** Rationale: agent surface is still small (one `ChatService` + four providers), so doing PydanticAI first folds three pending reworks (LangChain → PydanticAI, `LLMProvider` Protocol → ABC, `_flight_client` back-door → DI) into one change and lets Phase 6's `Message` SQLModel target PydanticAI's `ModelMessage` from the start instead of being retrofitted. The `REQ-p5-*` requirement IDs keep their `p5` prefix as historical schedule labels.
- 2026-05-15 (PR #6 review): Promote Postgres + Redis + docker-compose into v1 (now Phase 6 after the 2026-06-02 swap); replaces in-memory `_histories` and `AUTH_USERS` env-seed with `psycopg` async + `sqlmodel` ORM and a single `docker compose up`. ADR-006.
- 2026-05-15 (PR #6 review): Migrate from LangChain to PydanticAI (now Phase 5 after the 2026-06-02 swap) — rationale: lighter and easier to test. ADR-001 → Superseded; ADR-007.
- 2026-05-15 (PR #6 review): Drop rate limiting from v1 hardening (ADR-009). `slowapi` and the Redis-backed rate-limiter v2 row are obsolete.
- 2026-05-15 (PR #6 review): Outbound HTTP uses **`pyreqwest`** (not `aiohttp`/`httpx`); database access uses **`psycopg` async + `sqlmodel`** ORM. ADR-008.
- 2026-05-15 (PR #6 review): LLM provider abstraction must support **dynamic Ollama model discovery from the host** AND **real cloud LLMs via API key** (OpenAI + Anthropic). Stub-only providers are unacceptable.
- 2026-05-15 (PR #6 review): Tool JSON contract (Phase 4.6) must map onto Amadeus / Skyscanner / Google Flights without lossy field collapses, so the real Phase 7 client lands without rework.
- 2026-05-15 (PR #6 review): CI reset (Phase 4.3) — drop the nightly schedule; lint + unit + integration on every PR push, required for merge; E2E retained only for auth flow + real travel API, gated on credentials.
- 2026-05-15 (PR #6 review): Phase 4.4 introduces a `MockLLMStream` fixture so default `pytest` no longer calls Ollama; the `slow` marker is removed at that point. (Today: marker still in `pyproject.toml`.)
- 2026-05-15 (PR #6 review): ruff line length raised 100 → 120 and routes migrated to `Annotated[T, Depends(...)]` — both shipped in **Phase 4.3** as `REQ-lint-line-length-120` + `REQ-annotated-depends`. (Today: line length still 100, routes still use bare `Depends()`.)
- 2026-05-15 (PR #6 review): Phase 4.1, REQ-auth-backend, and REQ-ci-cd-pipeline reclassified as **Partial / Broken**; their unfinished slices reopened as REQ-login-page (4.2), REQ-llm-provider-ui-fix (4.2), and REQ-ci-reset (4.3).
- Phase 4.1 (shipped, partial): Provider + model selection is per-session and persisted in localStorage; selecting a different provider creates a new session rather than mutating the active one — but the in-browser model selector does not produce a working session today.
- PR #3 (shipped): `ChatInterface.tsx` decomposition uses the **hooks-shape** variant (`parseSSE` + `useSSEStream` + `useChat`); the reducer-based variant is superseded.
- [Phase ?]: Phase 4.9-02: UserRepository Protocol structural typing — Phase 6 swaps EnvUserRepository for PostgresUserRepository by overriding one FastAPI dependency

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- ~~**Critical**: app non-functional in the browser — no login page (every `/api/*` returns 401) and the in-UI model selector does not produce a working session.~~ **Resolved in Phase 4.2.**
- ~~**Critical**: CI runs nightly E2E with no useful signal and runs Ollama in E2E rather than auth flow + real travel APIs.~~ **Resolved in Phase 4.3.**
- ADR transitions queued: ADR-001 (LangChain) → Superseded by ADR-007 (PydanticAI) in **Phase 5** *(swapped from Phase 6 on 2026-06-02)*; ADR-002 (Global Chat Store) → Obsolete once **Phase 6** lands PG-backed history *(swapped from Phase 5)*; ADR-008 (`pyreqwest`) lands in Phase 7.
- Phase 6 retires the `AUTH_USERS` env-seeded user store *(was Phase 5 before the 2026-06-02 swap)*. Phase 4.2's quick-and-dirty login keeps it as the user source until then.
- Coverage debt: backend coverage is at the 60% CI floor — 80% target lands in Phase 8 (`REQ-backend-test-coverage-60` + `REQ-coverage-ratchet-80`).
- Phase 8 gap: security headers + Chakra-aware `rehype-sanitize` not yet shipped (`REQ-security-headers`). Note: rate limiting is **not** part of v1 (ADR-009); the previous "REQ-security-hardening" line item in older drafts has been split, and the rate-limit slice deleted.
- ~~**Sequencing risk** (caught by 2026-05-15 follow-up review): Phase 5 builds PG-backed message history against LangChain's `BaseChatMessageHistory` shape, then Phase 6 swaps the agent runtime to PydanticAI which uses a different `ModelMessage` shape — the `Message` SQLModel will likely need rework.~~ **Resolved on 2026-06-02 by swapping Phase 5 ↔ Phase 6 per PR #20 review** — PydanticAI now lands first, so the `Message` table is shaped against `ModelMessage` directly with no forward-migration debt.
- **User-data migration gap**: Phase 4.2 keeps `AUTH_USERS` env-seed; **Phase 6** retires it via a PG bootstrap script *(was Phase 5 before the 2026-06-02 swap)*. The migration story (do existing JWTs invalidate? do passwords carry over?) is unspecified — to be defined when Phase 6 is planned.

## Deferred Items

Items acknowledged and carried forward; tracked in REQUIREMENTS.md "v2 Requirements" and "Out of Scope":

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Auth | JWT token revocation / deny-list (AUTH2-01) | v2 | 2026-05-14 |
| Auth | User registration endpoint (AUTH2-02) | v2 | 2026-05-14 |
| Tooling | `openapi-typescript` codegen (TOOL-01) | v2 | 2026-05-14 |
| Tooling | Playwright frontend E2E (TOOL-02) | v2 | 2026-05-14 |
| Travel | Hotel / restaurant / weather tools (TRAVEL-01..03) | v2 | 2026-05-14 |
| Travel | Multi-city / multi-leg trip planning (TRAVEL-04) | v2 | 2026-05-14 |
| Architecture | DSPy migration (ARCH-01) | v2 | 2026-05-14 |
| Security | Rate limiting (`slowapi`, Redis-backed limiter) | **Out of scope (ADR-009)** | 2026-05-15 |
| Architecture | GraphQL API migration | **Out of scope** | 2026-05-15 |

## Session Continuity

Last session: 2026-06-05T04:44:14.286Z
Stopped at: Phase 7 context gathered
Resume file: .planning/phases/07-real-flight-api/07-CONTEXT.md
