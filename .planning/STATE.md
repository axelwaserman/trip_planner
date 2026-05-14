# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-14)

**Core value:** A user can hold a natural conversation with an AI agent, watch it reason and call travel tools live, and trust that the results are structured, sanitized, and rendered usefully — across multiple LLM providers selected from the UI.
**Current focus:** Phase 4.2 — Structured Tool Output (next phase to plan + execute).

## Current Position

Phase: 4.2 of 6 (Structured Tool Output)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-05-14 — `gsd-roadmapper` resumed; ROADMAP.md and STATE.md materialized to align with already-shipped Phases 1-4.1.

Progress: [████░░░░░░] ~44% (4 of 9 phases complete: 1, 2, 3, 4.1)

## Performance Metrics

**Velocity:**
- Total plans completed: retroactive (PRs #1-#5 + Phase 4.1) — pre-GSD-tracking, no per-plan durations recorded
- Average duration: n/a
- Total execution time: n/a

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation & FastAPI Setup | retro | shipped 2025-11-06 → 2025-11-08 | n/a |
| 2. LangChain Integration & Chat Agent | retro | shipped 2025-11-08 → 2025-11-10 | n/a |
| 3. Mock Flight Search Tool | retro | shipped 2025-11-10 → 2025-11-14 | n/a |
| 4.1. LLM Provider UI Config | retro | shipped 2026-05-13 | n/a |

**Recent Trend:**
- Last 5 plans: not tracked (pre-GSD)
- Trend: n/a — first GSD-tracked phase is 4.2

*Updated after each plan completion.*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Phase 4 (synthesis): Adopt the product-phase numbering scheme from the legacy `/ROADMAP.md` as authoritative; engineering items run as a cross-cutting Quality Workstream that lands in Phases 4.4 / 5 / 6.
- Phase 4 (synthesis): ADR-002 (Global Chat Store) is **Deprecated** — `ChatService._histories` already provides per-instance session storage; `REQ-session-management` and `REQ-di-lifespan-fix` are N/A.
- Phase 4 (synthesis): Markdown sanitization adopts the IMPLEMENTATION_PLAN.md custom Chakra-aware `sanitizeConfig.ts` variant (lands in Phase 6 under REQ-security-hardening); the default `rehype-sanitize` config is forbidden — it strips Chakra-rendered tables.
- PR #3 (shipped): `ChatInterface.tsx` decomposition uses the **hooks-shape** variant (`parseSSE` + `useSSEStream` + `useChat`); the reducer-based variant is superseded.
- Phase 4.1 (shipped): Provider + model selection is per-session and persisted in localStorage; selecting a different provider creates a new session rather than mutating the active one.

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- Quality Workstream debt: backend coverage is currently at the 60% CI floor — must reach 80% in Phase 6 (REQ-backend-test-coverage-60 + REQ-coverage-ratchet-80).
- Quality Workstream debt: security-hardening (CSP / CORS allowlist / `slowapi` / Chakra-aware markdown sanitization) is not yet shipped — REQ-security-hardening lands in Phase 6.
- E2E tests still require Ollama and remain gated to `workflow_dispatch` / `schedule`; not a blocker, but a known limitation that constrains what PR CI can verify.

## Deferred Items

Items acknowledged and carried forward; tracked in REQUIREMENTS.md "v2 Requirements" and "Out of Scope":

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Persistence | PostgreSQL session/message persistence (PERSIST-01) | v2 | 2026-05-14 |
| Deployment | Docker / docker-compose with `OLLAMA_BASE_URL` override (DEPLOY-01) | v2 | 2026-05-14 |
| Auth | JWT token revocation / deny-list (AUTH2-01) | v2 | 2026-05-14 |
| Auth | User registration endpoint (AUTH2-02) | v2 | 2026-05-14 |
| Security | Redis-backed rate limiter (SEC2-01) | v2 | 2026-05-14 |
| Tooling | `openapi-typescript` codegen (TOOL-01) | v2 | 2026-05-14 |
| Tooling | Playwright frontend E2E (TOOL-02) | v2 | 2026-05-14 |
| Travel | Hotel / restaurant / weather tools (TRAVEL-01..03) | v2 | 2026-05-14 |
| Travel | Multi-city / multi-leg trip planning (TRAVEL-04) | v2 | 2026-05-14 |
| Architecture | DSPy / GraphQL migration (ARCH-01, ARCH-02) | v2 | 2026-05-14 |

## Session Continuity

Last session: 2026-05-14 17:34
Stopped at: `gsd-roadmapper` resume-from-partial — wrote ROADMAP.md and STATE.md aligned with the existing PROJECT.md and REQUIREMENTS.md.
Resume file: None — next action is `/gsd-plan-phase 4.2`.
