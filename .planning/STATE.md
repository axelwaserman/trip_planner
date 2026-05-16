---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Re-platform
status: executing
stopped_at: Phase 4.2 UI-SPEC approved
last_updated: "2026-05-16T07:55:41.698Z"
last_activity: 2026-05-16 -- learnings extracted for Phase 04.2
progress:
  total_phases: 15
  completed_phases: 0
  total_plans: 6
  completed_plans: 5
  percent: 83
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-15)

**Core value:** A user can authenticate via a real login page, pick an LLM provider (a local Ollama model discovered from the host, or a cloud provider via API key), hold a natural conversation with the agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully.
**Current focus:** Phase 04.2 — unbreak-the-app

## Current Position

Phase: 04.2 (unbreak-the-app) — EXECUTING
Plan: 1 of 6
Status: Executing Phase 04.2
Last activity: 2026-05-16 -- learnings extracted for Phase 04.2

Progress: [██░░░░░░░░░░░░░] ~13% (2 of 15 phases fully complete: 2, 3; Phase 1 and Phase 4.1 partial)

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

**Recent Trend:**

- Last 5 plans: not tracked (pre-GSD)
- Trend: n/a — first GSD-tracked phase is 4.2

*Updated after each plan completion.*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 2026-05-15 (PR #6 review): Promote Postgres + Redis + docker-compose into v1 (Phase 5); replaces in-memory `_histories` and `AUTH_USERS` env-seed with `psycopg` async + `sqlmodel` ORM and a single `docker compose up`. ADR-006.
- 2026-05-15 (PR #6 review): Migrate from LangChain to PydanticAI in Phase 6 — rationale: lighter and easier to test; LangChain currently works so the migration is sequenced after the PG+compose re-platform. ADR-001 → Superseded; ADR-007.
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

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- **Critical**: app non-functional in the browser — no login page (every `/api/*` returns 401) and the in-UI model selector does not produce a working session. Phase 4.2 (`REQ-login-page`, `REQ-llm-provider-ui-fix`) unblocks this.
- **Critical**: CI runs nightly E2E with no useful signal and runs Ollama in E2E rather than auth flow + real travel APIs. Phase 4.3 (`REQ-ci-reset`) fixes this.
- ADR transitions queued: ADR-001 (LangChain) → Superseded by ADR-007 (PydanticAI) in Phase 6; ADR-002 (Global Chat Store) → Obsolete once Phase 5 lands PG-backed history; ADR-008 (`pyreqwest`) lands in Phase 7.
- Phase 5 retires the `AUTH_USERS` env-seeded user store. Phase 4.2's quick-and-dirty login keeps it as the user source for now; the cleanup happens at Phase 5.
- Coverage debt: backend coverage is at the 60% CI floor — 80% target lands in Phase 8 (`REQ-backend-test-coverage-60` + `REQ-coverage-ratchet-80`).
- Phase 8 gap: security headers + Chakra-aware `rehype-sanitize` not yet shipped (`REQ-security-headers`). Note: rate limiting is **not** part of v1 (ADR-009); the previous "REQ-security-hardening" line item in older drafts has been split, and the rate-limit slice deleted.
- **Sequencing risk** (caught by 2026-05-15 follow-up review): Phase 5 builds PG-backed message history against LangChain's `BaseChatMessageHistory` shape, then Phase 6 swaps the agent runtime to PydanticAI which uses a different `ModelMessage` shape — the `Message` SQLModel will likely need rework. Same risk at the provider layer: Phase 4.5's `LLMProvider` Protocol mirrors LangChain's `BaseChatModel`; PydanticAI is `Agent`-shaped. Phase 4.5 + Phase 5 success criteria carry rework-risk notes; revisit ordering before planning Phase 5.
- **User-data migration gap**: Phase 4.2 keeps `AUTH_USERS` env-seed; Phase 5 retires it via a PG bootstrap script. The migration story (do existing JWTs invalidate? do passwords carry over?) is unspecified — to be defined when Phase 5 is planned.

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

Last session: 2026-05-15T13:51:20.795Z
Stopped at: Phase 4.2 UI-SPEC approved
Resume file: .planning/phases/04.2-unbreak-the-app/04.2-UI-SPEC.md
