## Conflict Detection Report

### BLOCKERS (0)

(BLOCKERS count remains 0. Cross-ref cycle NOW.md ↔ ROADMAP.md broken: ROADMAP.md edited to remove the NOW.md back-link; classification ROADMAP-md-d4a7e2b1.json patched to clear cross_refs. Prose mention of `ROADMAP.md` in `NOW.md:97` retained — the cycle rule scopes to markdown link references per the gsd-doc-synthesizer agent contract, not narrative prose.)

---

### WARNINGS (3)

[WARNING] Competing acceptance variants for REQ-frontend-testing-refactor
  Found: /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md Phase 4 prescribes a custom-hooks decomposition (parseSSE.ts, useSSEStream.ts, useChat.ts) with acceptance "ChatInterface.tsx under 200 lines". /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md Task 5 prescribes a useReducer-based decomposition (chatReducer + ChatAction discriminated union + useChatStream) with acceptance "Declarative state updates; imperative index tracking removed".
  Impact: Both prescribe different shapes for the same target file; synthesis cannot pick a winner without losing the rejected approach's intent. Note that PR #3 (`feat(frontend): add Vitest testing + decompose ChatInterface.tsx`) has already been merged — likely realised one of the two; the doc state has not been reconciled.
  source: /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md (Phase 4 table + acceptance), /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md (Task 5)
  -> Choose one variant and update the other doc to match (or supersede), or split into two requirements: one for the hooks-shape decomposition (already done) and a follow-up for reducer-based state. Consider checking the merged PR #3 to determine which variant landed and reconcile docs accordingly.

[WARNING] Competing acceptance variants for REQ-markdown-xss-sanitization (rehype-sanitize config)
  Found: /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md Phase 5 requires a custom sanitizeConfig.ts that preserves Chakra UI table elements when sanitizing markdown. /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md Task 10 prescribes a 5-minute drop-in of the default rehype-sanitize plugin with no custom config.
  Impact: The default config will strip Chakra-specific HTML used to render tables, breaking flight-result rendering. Picking the simpler Task 10 form silently regresses Phase 5's UX intent.
  source: /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md (Phase 5 changes table), /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md (Task 10)
  -> Adopt the Phase 5 custom-config variant (broader scope, considers UX) and supersede Task 10. Or treat Task 10 as a stop-gap to be replaced by Phase 5 work.

[WARNING] Competing phase-numbering schemes for the project as a whole
  Found: /Users/axel/code/trip_planner/ROADMAP.md uses product phases (Phase 1 Foundation, Phase 2 LangChain, Phase 3 Mock Tool, Phase 4 Provider Flexibility, Phase 5 Real API, Phase 6 Production). /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md (dated 2026-05-13) uses engineering phases on the same numbers (Phase 0 Bug Fixes, Phase 1 Auth, Phase 2 CI/CD, Phase 3 Backend Coverage, Phase 4 Frontend Testing, Phase 5 Security, Phase 6 Coverage 80%).
  Impact: Phase numbers collide. "Phase 4" in NOW.md/ROADMAP.md means LLM Provider Flexibility; "Phase 4" in IMPLEMENTATION_PLAN.md means Frontend Testing. Roadmapper output (ROADMAP.md, REQUIREMENTS.md) cannot use bare "Phase N" without disambiguation.
  source: /Users/axel/code/trip_planner/ROADMAP.md, /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md, /Users/axel/code/trip_planner/NOW.md
  -> Choose one phasing scheme as authoritative for the rebuilt roadmap. Recommended: keep product phases (ROADMAP.md numbering) and re-classify IMPLEMENTATION_PLAN's items as workstreams or sub-phases (e.g. "Quality Workstream: 0a Bug Fixes, 0b Auth, 0c CI ..." cross-cutting product Phase 4).

---

### INFO (8)

[INFO] Auto-resolved: ADR-002 (Global Chat Store) marked Deprecated by source itself
  Note: /Users/axel/code/trip_planner/ARCHITECTURE.md (lines 343-365) classifies ADR-002 as Status: Deprecated, replaced by Session Management. /Users/axel/code/trip_planner/NOW.md (2025-11-14) confirms the global store never existed in code: "No global `_global_chat_store` exists - was a misunderstanding." /Users/axel/code/trip_planner/CLAUDE.md says "There is no global store." Decisions.md preserves the ADR for history but flags it as inactive. No conflict requires user action.
  source: /Users/axel/code/trip_planner/ARCHITECTURE.md (ADR-002), /Users/axel/code/trip_planner/NOW.md, /Users/axel/code/trip_planner/CLAUDE.md

[INFO] Auto-resolved: current LLM model is qwen3:4b (not gpt-oss20b)
  Note: /Users/axel/code/trip_planner/README.md says Ollama runs "gpt-oss20b". /Users/axel/code/trip_planner/ARCHITECTURE.md mentions qwen3:8b. /Users/axel/code/trip_planner/NOW.md, /Users/axel/code/trip_planner/ROADMAP.md, /Users/axel/code/trip_planner/phases/phase-4.1-llm-provider-config.md (all dated 2025-11-14), and /Users/axel/code/trip_planner/CLAUDE.md all converge on qwen3:4b. Lower-precedence and older sources lose. constraints.md (CON-llm-provider-current) recorded qwen3:4b as authoritative.
  source: /Users/axel/code/trip_planner/README.md (stale), /Users/axel/code/trip_planner/ARCHITECTURE.md (older), /Users/axel/code/trip_planner/NOW.md, /Users/axel/code/trip_planner/ROADMAP.md, /Users/axel/code/trip_planner/phases/phase-4.1-llm-provider-config.md, /Users/axel/code/trip_planner/CLAUDE.md

[INFO] CI E2E model mismatch: workflow pulls llama3.2:3b, runtime default is qwen3:4b
  Note: /Users/axel/code/trip_planner/.github/workflows/ci.yml runs `ollama pull llama3.2:3b` (line 119) for the E2E job, while the documented runtime default per NOW.md/CLAUDE.md is qwen3:4b. Not a blocker — the E2E job is gated to manual/scheduled runs, so PR CI isn't affected. Worth a Quality Workstream backlog ticket to align CI with the documented runtime default.
  source: /Users/axel/code/trip_planner/.github/workflows/ci.yml:119 (`ollama pull llama3.2:3b`), /Users/axel/code/trip_planner/NOW.md, /Users/axel/code/trip_planner/CLAUDE.md

[INFO] Auto-resolved: backend project layout follows CLAUDE.md, not ARCHITECTURE.md draft
  Note: /Users/axel/code/trip_planner/ARCHITECTURE.md project-structure section depicts a future-state layout with `backend/app/infrastructure/clients/`, `backend/app/domain/`, `backend/app/services/`. /Users/axel/code/trip_planner/CLAUDE.md describes the actual current layout: `backend/app/tools/flight_search.py`, `backend/app/tools/flight_client.py`, `backend/app/models.py`, `backend/app/chat.py`. CLAUDE.md describes the live code state and wins. constraints.md (CON-project-layout) reflects the resolution.
  source: /Users/axel/code/trip_planner/ARCHITECTURE.md (Project Structure), /Users/axel/code/trip_planner/CLAUDE.md (Backend section)

[INFO] Auto-resolved: pre-phase-4 Tasks 1 (sessions) and 9 (DI) are obsolete (N/A)
  Note: /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md prescribes work to introduce SessionStore + remove `@lru_cache` singletons. /Users/axel/code/trip_planner/NOW.md (2025-11-14) explicitly supersedes both: "Session management already exists (ChatService stores sessions in `_histories`). No global `_global_chat_store` exists - was a misunderstanding." and "Dependency injection fixes (no issues found)". /Users/axel/code/trip_planner/CLAUDE.md confirms current code already follows the desired pattern. requirements.md flags REQ-session-management and REQ-di-lifespan-fix as DONE / N/A.
  source: /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md (Tasks 1, 9), /Users/axel/code/trip_planner/NOW.md, /Users/axel/code/trip_planner/CLAUDE.md

[INFO] CORRECTED: flight tool returns plain-text strings, not JSON; pre-phase-4-refactor Task 4 description was accurate
  Note: The previous auto-resolution for this entry was incorrect. Verification of /Users/axel/code/trip_planner/backend/app/tools/flight_search.py:146-177 shows `search_flights()` builds a multi-line plain-text string (e.g. `f"Found {len(flights)} flight(s) from {origin} to {destination}..."` followed by `"\n".join(result_lines)` returning numbered, multi-line per-flight blocks). It does NOT return JSON. /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md Task 4's characterization of the output as "verbose formatted strings" is therefore correct, and the original conflict (between Task 4 and the ARCHITECTURE.md / CLAUDE.md descriptions of the tool returning JSON with `status`, `query`, `results`) is real — those docs are aspirational/stale, not current. REQ-tool-json-output (Phase 4.2) is the work that actually transitions the tool to structured JSON output; that work has not yet shipped.
  source: /Users/axel/code/trip_planner/backend/app/tools/flight_search.py:146-177 (verified plain-text output), /Users/axel/code/trip_planner/phases/pre-phase-4-refactor.md (Task 4), /Users/axel/code/trip_planner/ARCHITECTURE.md (LangChain Integration — stale), /Users/axel/code/trip_planner/CLAUDE.md (stale)

[INFO] IMPLEMENTATION_PLAN.md status table is out of date relative to merged PRs
  Note: /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md (dated 2026-05-13) lists Phases 1, 2, and 4 as TODO, but git history shows Phase 1 (Auth — PR #4 `feat(auth): implement JWT auth with pwdlib password hashing`), Phase 2 (CI/CD — PR #2 `feat(ci): add GitHub Actions CI pipeline`), and Phase 4 (Frontend Testing — PR #3 `feat(frontend): add Vitest testing + decompose ChatInterface.tsx`) have all been merged to master. Synthesizer flagged each requirement (REQ-auth-hardening, REQ-ci-cd-pipeline, REQ-frontend-testing-refactor) with the corrected status in requirements.md so the roadmapper does not re-execute completed work.
  source: /Users/axel/code/trip_planner/.planning/IMPLEMENTATION_PLAN.md (Progress table), git log on master (commits 7a5166c, d397030, 83ce919)

[INFO] README.md cross-references files that do not exist
  Note: /Users/axel/code/trip_planner/README.md links to `./PLAN.md` and `./copilot-instructions.md`. Neither file is present in the repository today. The README is partially stale; the authoritative onboarding doc is `CLAUDE.md` and the authoritative implementation plan is `.planning/IMPLEMENTATION_PLAN.md`. Roadmapper may want to refresh README.md as a downstream cleanup task.
  source: /Users/axel/code/trip_planner/README.md (cross_refs)

[INFO] All 9 ingested docs were classified DOC at parent level; ARCHITECTURE.md ADRs were extracted as locked decisions per orchestrator instruction
  Note: classifications/ARCHITECTURE-7c4e9d21.json carries `type: DOC` and `locked: false` at the parent-doc level, but the document body contains 5 explicit ADR-* sections (4 Accepted, 1 Deprecated). The orchestrator note for this synthesis run instructed: "Extract these as locked decisions despite the parent doc type." decisions.md treats ADR-001, ADR-003, ADR-004, ADR-005 as locked; ADR-002 is recorded as Deprecated/inactive. No actual ADR/SPEC/PRD-typed docs were ingested in this batch — synthesizer ran exclusively on DOC sources, so PRD-style competing-acceptance and SPEC-vs-ADR conflict passes had no input to find.
  source: /Users/axel/code/trip_planner/.planning/intel/classifications/ARCHITECTURE-7c4e9d21.json, orchestrator prompt
