# Synthesis Summary

> Entry point for `gsd-roadmapper`. Read this first; the per-type intel files (`decisions.md`, `requirements.md`, `constraints.md`, `context.md`) hold the detail.

## Inputs

- **Source classifications:** `/Users/axel/code/trip_planner/.planning/intel/classifications/` (9 files)
- **Mode:** new (bootstrapping `.planning/`)
- **Precedence:** ADR > SPEC > PRD > DOC (default)
- **Manifest overrides:** none

## Doc counts by type

| Type | Count |
|------|-------|
| ADR  | 0     |
| SPEC | 0     |
| PRD  | 0     |
| DOC  | 9     |

All 9 source documents were classified `DOC` at the parent-doc level. **ARCHITECTURE.md contains 5 embedded ADR sections** (`ADR-001` through `ADR-005`) which the orchestrator instructed to extract as locked decisions despite the parent doc type. Treated accordingly in `decisions.md`.

## Decisions extracted

- **Total ADRs extracted:** 5
- **Locked (Accepted):** 4
  - ADR-001 LangChain 1.0 with `bind_tools()` — `ARCHITECTURE.md`
  - ADR-003 SSE streaming — `ARCHITECTURE.md`
  - ADR-004 Pydantic models for all data structures — `ARCHITECTURE.md`
  - ADR-005 Mock-first external API integration — `ARCHITECTURE.md`
- **Deprecated (recorded for history, not active):** 1
  - ADR-002 Global Chat Store (superseded by per-instance `ChatService._histories`)
- **Implicit decisions** (project rules promoted to ADR-candidate status): 7 — see `decisions.md` "Implicit decisions" section.

## Requirements extracted

- **Total:** 18

| ID | Status |
|----|--------|
| REQ-bug-fixes-cleanup | MERGED (PR #1) |
| REQ-auth-hardening | DONE (PR #4) per git; plan doc still TODO |
| REQ-ci-cd-pipeline | DONE (PR #2) per git; plan doc still TODO |
| REQ-backend-test-coverage-60 | TODO |
| REQ-frontend-testing-refactor | DONE (PR #3) per git; competing decomposition variants flagged |
| REQ-security-hardening | TODO |
| REQ-coverage-ratchet-80 | TODO |
| REQ-session-management | DONE / N/A (premise was incorrect) |
| REQ-llm-provider-abstraction | PARTIAL |
| REQ-llm-provider-ui-config | COMPLETE |
| REQ-streamevent-hierarchy | NOT STARTED |
| REQ-tool-json-output | NOT STARTED (next phase per Phase 4.1 doc → 4.2) |
| REQ-error-handling-feedback | NOT STARTED |
| REQ-structured-logging | NOT STARTED |
| REQ-pydantic-validators | NOT STARTED |
| REQ-test-fixture-dedup | NOT STARTED |
| REQ-di-lifespan-fix | N/A (already correct) |
| REQ-markdown-xss-sanitization | NOT STARTED (subsumed by REQ-security-hardening; competing config variants flagged) |

Acceptance criteria are listed per requirement in `requirements.md`.

## Constraints extracted

- **Total:** 28
- Breakdown by type:
  - api-contract: 4 (`CON-stream-event-protocol`, `CON-flight-tool-output-schema-current`, `CON-providers-api`, `CON-session-lifecycle-api`)
  - schema: 2 (`CON-error-hierarchy`, `CON-pydantic-validators-business-rules`)
  - protocol: 9 (async-io, ci-pr-gates, ci-concurrency, auth-jwt, cors-origin-allowlist, security-headers, rate-limiting, markdown-sanitization, no-lru-cache-singletons)
  - nfr: 6 (test-pyramid, test-no-network-no-ollama, coverage-floor-60, coverage-floor-80, frontend-coverage-future)
  - tooling: 7 (mypy-strict, package-manager-uv, format-lint, test-aaa-pattern, runtime-versions, tech-stack-versions, llm-provider-current, project-layout)

## Context topics

10 narrative topics captured in `context.md`:

1. Project identity and purpose
2. Current development status
3. Two parallel phasing schemes
4. Architectural philosophy
5. Named patterns
6. LangChain integration
7. Frontend structure
8. Test layout and markers
9. Just-based command runner
10. GSD framework usage; Deferred items; Known accepted limitations; Pre-Phase 4 historical context; Cross-reference graph notes

## Conflicts

- **BLOCKERS:** 0 (cycle resolved by editing ROADMAP.md to drop NOW.md back-link)
- **WARNINGS (competing variants):** 3
  - REQ-frontend-testing-refactor — hooks vs reducer decomposition strategies
  - REQ-markdown-xss-sanitization — default vs custom Chakra-aware sanitize config
  - Phase numbering scheme — product phases vs engineering phases share numbers
- **INFO (auto-resolved):** 8 (model name, project layout, deprecated ADR, stale tool description, plan-doc vs git status drift, broken README cross-refs, all-DOC ingest, obsolete pre-phase-4 tasks)

Detail in `/Users/axel/code/trip_planner/.planning/INGEST-CONFLICTS.md`.

## Pointers

- Decisions: `/Users/axel/code/trip_planner/.planning/intel/decisions.md`
- Requirements: `/Users/axel/code/trip_planner/.planning/intel/requirements.md`
- Constraints: `/Users/axel/code/trip_planner/.planning/intel/constraints.md`
- Context: `/Users/axel/code/trip_planner/.planning/intel/context.md`
- Conflicts report: `/Users/axel/code/trip_planner/.planning/INGEST-CONFLICTS.md`

## Status

**APPROVED FOR ROUTING** — 0 BLOCKERS. 3 WARNINGs accepted by user; `gsd-roadmapper` should reconcile the competing variants in PROJECT.md / ROADMAP.md / REQUIREMENTS.md per guidance below.
