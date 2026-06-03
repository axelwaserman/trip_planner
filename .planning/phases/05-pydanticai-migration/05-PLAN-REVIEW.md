---
phase: 5
slug: pydanticai-migration
status: needs_revision
created: 2026-06-03
plans_reviewed: 6
checks_total: 9
checks_passed: 6
checks_failed: 3
---

# Phase 5 — Plan Review

## 1. Verdict: NEEDS_REVISION

The six-plan set demonstrates strong domain coverage: every ROADMAP success criterion (SC-1..SC-6) maps to at least one plan's `must_haves`, every D-XX from CONTEXT.md is referenced in at least one task, and all four anti-pattern locks are explicitly named and tested. The wave dependency ordering (0 → 1 → 2 → 3 → 4 → 5) is internally consistent, and the project-rule callouts (`/dignified-python`, ABC over Protocol, StrEnum, Settings tunables, `httpx` carve-out, `uv` exclusivity, package legitimacy gate) are visible throughout.

However, **Wave 1 leaves the codebase in a non-importable state**, and one Wave-0 verify command in the same wave is materially impossible to run. Three findings rise to BLOCKER. The phase will not deliver SC-3 cleanly without fixing the protocol-shim sequencing in plan 05-02. Two MEDIUM/HIGH findings about `ConversationStore.list_for_user` semantics and ADR-007 file-creation guidance round out the required revisions.

The migration's centerpiece (plan 05-04) is well-scoped and faithful to RESEARCH §3 streaming arch and Pitfalls 1/3/6. Plans 05-05 and 05-06 are tightly contained; 05-01's golden-file capture is sound.

## 2. Coverage Matrix — ROADMAP Success Criteria

| SC | Description | Plans delivering | Status |
|----|-------------|------------------|--------|
| SC-1 | ChatService orchestrates per-session PydanticAI Agent; tool registration via PydanticAI; `_flight_client` back-door replaced by RunContext | 05-04 (Tasks 1, 3, 5) | ✓ |
| SC-2 | Discriminated StreamEvent union over SSE preserved unchanged for FE; refactored to `StreamEvent(ABC)` w/ 5 concrete subclasses | 05-01 (Task 1 — golden), 05-02 (Task 3) | ✓ |
| SC-3 | LLMProvider/BoundProvider Protocol → ABC; concrete providers explicit subclasses | 05-02 (Task 1), 05-03 (Tasks 1–3) | ✗ — see Finding A1 |
| SC-4 | langchain* (and per Pitfall 9, langgraph) removed from pyproject.toml; pydantic-ai added; uv lock consistent | 05-05 (Tasks 1–3) | ✓ |
| SC-5 | MockLLMStream updated for PydanticAI agent surface; default pytest fast and offline | 05-04 (Task 2, Task 4) | ✓ |
| SC-6 | ADR-001 → Superseded; ADR-007 → Locked; ARCHITECTURE.md + PROJECT.md updated | 05-06 (Tasks 1–3) | partial — see Finding F1 |

## 3. Decision Coverage — D-01..D-21

| D-XX | Subject | Plans referencing | Status |
|------|---------|-------------------|--------|
| D-01 | Single LLMProvider(ABC); BoundProvider retires | 05-02 (Task 1) | ✓ |
| D-02 | ABC surface methods | 05-02 (Task 1, interfaces) | ✓ |
| D-03 | ABC, not Protocol | 05-01, 05-02 (Task 1), 05-03 (Tasks 1–2) | ✓ |
| D-04 | Factory returns concrete LLMProvider; _agents per session | 05-03 (Task 3), 05-04 (Task 3) | ✓ |
| D-05 | ChatDeps frozen dataclass | 05-01 (Task 2), 05-02 (Task 2), 05-04 (Task 3) | ✓ |
| D-06 | search_flights gains ctx: RunContext[ChatDeps]; back-door deleted | 05-01 (Task 4), 05-04 (Task 1, Task 3) | ✓ |
| D-07 | Tool registration via Agent constructor | 05-04 (Task 3) | ✓ |
| D-08 | ConversationStore(ABC) + InMemory | 05-02 (Task 2), 05-04 (Task 3) | ✓ — but see Finding A2 |
| D-09 | _metadata/_last_activity stay on ChatService | 05-02 (Task 2), 05-04 (Task 3) | ✓ |
| D-10 | _bound_providers → _agents | 05-04 (Task 3) | ✓ |
| D-11 | InMemory storage = list[ModelMessage] natively | 05-02 (Task 2), 05-04 (Task 3) | ✓ |
| D-12 | All four providers emit ThinkingEvent best-effort | 05-03 (Tasks 1–2), 05-04 (Task 3), 05-01 (Task 2) | ✓ |
| D-13 | Per-provider gated acceptance tests | 05-01 (Task 4 — skeletons) | ✓ |
| D-14 | OpenAI o-series → OpenAIResponsesModel dispatch | 05-02 (Task 3 — Settings), 05-03 (Tasks 2–3) | ✓ |
| D-15 | StreamEvent(BaseModel, ABC) base class | 05-02 (Task 3) | ✓ |
| D-16 | REQ-p5-stream-event-abc bundled into Phase 5 | 05-02 (Task 3 — frontmatter requirements) | ✓ |
| D-17 | MockLLMStream updated to drive PydanticAI surface | 05-04 (Task 2) | ✓ |
| D-18 | make_chat_service_with_mock_llm signature unchanged | 05-04 (Task 2, Task 4) | ✓ |
| D-19 | Default pytest fast and offline | 05-04 (Task 4 verify), 05-05 (Task 3) | ✓ |
| D-20 | langchain*/langgraph removed; pydantic-ai added | 05-05 (Task 2) | ✓ |
| D-21 | ADR-001 → Superseded; ADR-007 → Locked | 05-06 (Task 1) | ✓ |

All 21 decisions covered.

## 4. Findings

### A. Goal Coverage — FAIL (1 blocker, 1 high)

**A1. CRITICAL — BLOCKER — Plan 05-02 leaves the codebase non-importable.**
- Plan 05-02 Task 1 reduces `backend/app/llm/protocol.py` to a 3-line shim that re-exports only `LLMProvider`, NOT `BoundProvider`.
- Verified at `backend/app/llm/providers/{ollama,openai,anthropic,lmstudio}.py` that all four concrete providers do `from app.llm.protocol import BoundProvider` (ollama:48, lmstudio:52, anthropic:51, openai:37). After Wave 1, importing any of these modules raises `ImportError: cannot import name 'BoundProvider' from 'app.llm.protocol'`.
- Plan 05-02 Task 1 `<done>` claims `tests/unit/llm/test_protocol_abc.py` is "fully green" after the task — but that test file (per plan 05-01 Task 3) imports the four concrete providers to assert `issubclass(<Provider>, LLMProvider)`. Those imports will fail at collection.
- Same cascade hits `tests/unit/llm/test_factory.py` (line 21–24 imports providers), `tests/unit/llm/test_*_provider.py`, and any test transitively reaching `app.api.main`. The acknowledged "mypy strict will fail" framing in plan 05-02 (line 182) understates this — it's a runtime ImportError, not a static type error.
- Severity: BLOCKER because plan 05-02's verify command (`pytest tests/unit/llm/test_protocol_abc.py -v`) cannot pass, and SC-3 cannot be progressively delivered as the wave plan claims.
- Citation: 05-02-PLAN.md:174–183, 05-02-PLAN.md:186–189, 05-02-PLAN.md:319–321; cross-reference to providers at 05-03-PLAN.md:163, 174, 220, 228.
- **Required fix:** Either (a) widen Wave 1 to migrate the four provider files' import line `from app.llm.protocol import LLMProvider, BoundProvider` to `from app.llm.base import LLMProvider` and stub-delete the unused `BoundProvider` import in the same task (without rewriting `bind_tools`); or (b) keep `BoundProvider` in `protocol.py` (not the shim) until Wave 2 deletes it cleanly. Option (a) is the "pure rename + retype" the CONTEXT.md anti-pattern lock prescribes (05-02-PLAN.md:158).

**A2. HIGH — Plan 05-02 + 05-04 inconsistency on `Settings.ollama_reasoning_model_prefixes` removal.**
- Plan 05-02 Task 3 removes `Settings.ollama_reasoning_model_prefixes`. Plan 05-03 (Wave 2) removes `OllamaProvider.__init__`'s `reasoning_model_prefixes` param AND removes the factory's `reasoning_model_prefixes=...` keyword argument.
- After Wave 1 lands but before Wave 2: `factory.py` (line 97 today) still calls `OllamaProvider(..., reasoning_model_prefixes=self._settings.ollama_reasoning_model_prefixes, ...)`. The Settings field has just been removed — `AttributeError: 'Settings' object has no attribute 'ollama_reasoning_model_prefixes'` at runtime.
- Severity: HIGH — same root cause as A1 (Wave-1 mid-state breakage). Less catastrophic than A1 because the AttributeError surfaces only when `factory.build()` is called for `provider == "ollama"`, but `tests/unit/llm/test_factory.py` does call this in its dispatch tests.
- Citation: 05-02-PLAN.md:285 (removes Settings field) vs 05-03-PLAN.md:271–272 (removes factory call site) and current `backend/app/llm/factory.py:97`.
- **Required fix:** Defer the Settings field deletion to Wave 2 (plan 05-03 Task 3 — same task that removes the factory call site), OR make it a single same-task edit in plan 05-02 Task 3 that updates both `config.py` AND `factory.py:97` so the two halves stay in sync within the same wave.

### B. Locked-Decision Coverage — PASS

All 21 D-XX decisions are referenced in at least one plan's tasks (see Section 3). Anti-pattern locks (no two-tier shape, no `_flight_client` coexistence with RunContext, no `ProtocolProvider` adapter, no Agent-level mocking, no SSE wire change) are explicitly named in 05-01 (Task 1, Task 4), 05-02 (Task 1, Task 2 anti-pattern lock cite), 05-03 (Task 1, 2, 3), and 05-04 (Tasks 1, 2, 3).

### C. Anti-Pattern Locks — PARTIAL

C1. The Wave-1 transitional shim (plan 05-02 Task 1: a 3-line `protocol.py` re-export that exists for one wave then is deleted in plan 05-03 Task 3) sits in tension with the CONTEXT.md anti-pattern "Don't ship a `ProtocolProvider` adapter alongside the ABC — pure rename + retype, no backwards-compat shim". The plan acknowledges this lock at 05-02-PLAN.md:158. As implemented, the shim breaks the lock spirit (it IS a backwards-compat shim) AND breaks the runtime (Finding A1). MEDIUM severity by itself; rolled into A1 as the same fix path resolves it.

C2. All other anti-pattern locks are correctly enforced: `_flight_client` deletion (05-04 Task 1), no `_MockBoundProvider` adapter (05-04 Task 2), `FunctionModel` (Model-level mocking, not Agent-level — 05-04 Task 2 RESEARCH cite), SSE wire byte-equivalence (05-01 Task 1 golden file + 05-02 Task 3 verify).

### D. Wave / Dependency Ordering — PARTIAL

D1. Wave 0 (05-01) `depends_on: []` ✓. Wave 0 only writes test files; no production code modified ✓.

D2. Wave 1 (05-02) `depends_on: ["05-01"]` ✓ topologically — but its mid-wave state is broken (Findings A1 and A2). The wave is internally inconsistent: Task 1 claims `test_protocol_abc.py` turns green, but the production-code state at end of Task 1 makes that impossible.

D3. Wave 2 (05-03) `depends_on: ["05-02"]` ✓. Cleanly migrates each provider AND deletes the shim AND fixes the factory.

D4. Wave 3 (05-04) `depends_on: ["05-03"]` ✓. ChatService rewrite happens after providers expose `build_agent`.

D5. Wave 4 (05-05) `depends_on: ["05-04"]` ✓. Critical: dep removal happens AFTER all production imports are gone (verified at 05-04 Task 3 verification: `grep -rEn '^(from |import )langchain' backend/app` returns zero matches). This is correct. Pitfall 9 (langgraph) is included.

D6. Wave 5 (05-06) `depends_on: ["05-05"]` ✓. Docs after green code.

D7. Plan 05-03 Task 3 threat-model entry T-05.3-SC notes: "the imports executed here will FAIL if [pydantic-ai] isn't installed yet. The developer MUST run `uv add pydantic-ai` and `uv lock` before executing this plan." This is a **HIDDEN ORDERING DEPENDENCY** — Wave 2 imports `from pydantic_ai import Agent` etc., but plan 05-05 (Wave 4) is the one that adds `pydantic-ai` to `pyproject.toml`. The plan-set assumes the developer side-installs `pydantic-ai` before Wave 2 runs, but does not encode that step. MEDIUM.

### E. Anti-Shallow Execution — PASS

Every task has `<read_first>` listing files + CONTEXT/PATTERNS/RESEARCH anchors. Every `<action>` has concrete identifiers (`Agent[ChatDeps, str]`, `RunContext[ChatDeps]`, `ThinkingPart`, `OpenAIResponsesModel`, `FunctionModel`, `PartDeltaEvent`, `agent.iter()`, `ModelRequestNode`, `CallToolsNode`). Every `<verify><automated>` is a runnable `pytest` or shell command. The most idiom-heavy plan (05-04 Task 3) cites Pitfalls 1, 3, 6, the RESEARCH §3 match-block pattern, and Assumption A1.

### F. Validation Alignment (Sampling Density) — PARTIAL

F1. Sampling density: every plan has ≥ 50% of tasks with `<automated>` verify. Across the full phase execution ordering (4 + 3 + 3 + 5 + 3 + 3 = 21 tasks, two of which are blocking-human checkpoints in 05-04 and 05-05), no window of 3 consecutive tasks lacks an automated verify. ✓

F2. VALIDATION.md row coverage: every row in the Per-Task Verification Map (lines 41–71 of 05-VALIDATION.md) maps to a task somewhere in the plan set. The Wave-0 stubs (lines 81–95) all appear in plan 05-01's `files_modified` list.

F3. Plan 05-06 Task 1 `<verify>` includes `grep -q "Status: Locked" .planning/adrs/ADR-007-pydantic-ai.md`. The file does not exist at the start of the phase (`find /Users/axel/code/trip_planner/.planning -name "ADR-*"` returns no results). Task 1 `<action>` for ADR-007 says "Edit `.planning/adrs/ADR-007-pydantic-ai.md`" — implying it exists. The action for ADR-001 explicitly handles the missing-file case ("If the file does not exist, create it…"); ADR-007 needs the same explicit instruction. MEDIUM.

### G. Frontmatter / Requirement IDs — PASS

Both `REQ-pydantic-ai-migration` and `REQ-p5-stream-event-abc` appear in plan 05-01 and plan 05-02 `requirements:` blocks. Plans 05-03..05-06 only cite `REQ-pydantic-ai-migration` (correct — REQ-p5-stream-event-abc is fully delivered by plan 05-02 Task 3). All frontmatter blocks are well-formed YAML with `plan_id`, `phase`, `wave`, `depends_on`, `files_modified`, `requirements`, `must_haves`, `autonomous`.

### H. Project-Rule Compliance — PASS

H1. ABC over Protocol: enforced everywhere (plans 05-02 Task 1 + Task 2, 05-03 Tasks 1–2). The `/dignified-python` skill is invoked at every relevant task per CLAUDE.md.

H2. StrEnum vs Literal: PATTERNS.md callout #2 (line 1365) and plan 05-02 Task 3 `<behavior>` correctly preserve `Literal[...]` discriminators on subclasses (Pydantic discriminator machinery requires Literal; StrEnum is correct for cross-module taxonomies like `ProbeErrorCode`/`ErrorCode`). ✓

H3. Tunables on Settings: `openai_o_series_model_prefixes` lives on Settings (plan 05-02 Task 3, plan 05-03 Task 3). ✓

H4. `pyreqwest` for outbound HTTP: carve-out for `httpx` in `validate_config`/`list_models` is preserved per RESEARCH (plan 05-03 Task 1 line 153 + plan 05-05 line 106). No plan introduces `requests`/`aiohttp`. ✓

H5. `uv` exclusively: plan 05-05 Task 2 uses `uv add`, `uv remove`, `uv lock`, `uv sync` only. No pip/poetry/conda. ✓

### I. PATTERNS.md Fidelity — PASS

Every file in the 38-file PATTERNS.md classification table is referenced from a plan task's `<read_first>` block. New-file inventory (6 files: `chat/deps.py`, `chat/store.py`, `tests/unit/llm/providers/test_ollama_thinking.py`, `tests/unit/tools/test_flight_search_no_backdoor.py`, `tests/unit/test_dependencies.py`, `tests/unit/test_no_langchain_imports.py`) — all are flagged as new in their owning plans (05-01 Tasks 2, 3, 4; 05-02 Task 2). Where PATTERNS.md flags `no analog` (test_dependencies.py, test_no_langchain_imports.py), the plan explicitly states "no analog — genuinely new file" and references the closest neighbour. ✓

### Architectural Tier Compliance (Dimension 7c) — PASS

RESEARCH §"Architectural Responsibility Map" (line 84) places all seven Phase-5 capabilities in the API/Backend tier (LLM agent, per-session agent construction, tool DI, streaming extraction, conversation store, SSE wire, provider model selection). Plans 05-02..05-04 implement all of these in `backend/app/`. Frontend is explicitly untouched. SSE wire format is verified byte-equivalent. ✓

### Cross-Plan Data Contracts (Dimension 9) — PASS

The `list[ModelMessage]` shape flows: Wave 1 defines it (`store.py`); Wave 3 ChatService consumes it; Wave 3 fixture rewrite (`tests/fixtures/llm.py`) constructs it via real PydanticAI code path; Wave 4 dep manifest preserves the import availability. No plan strips data another plan needs. The `_metadata` dict stays on ChatService (D-09); `list_for_user` composition lives in ChatService and reads from `_metadata` (Finding A2 below addresses the gap). ✓

### CLAUDE.md Compliance (Dimension 10) — PASS

`mypy --strict` clean targets respected (plans defer to Wave 2 for full check). `ruff` line-length 120 is project-wide; not a per-plan concern. Plan 05-04 Task 3 explicitly preserves `pydantic-ai` async-only I/O. JWT/auth surface untouched per CONTEXT.md scope. `pyreqwest` carve-out preserved (Section H4).

### Research Resolution (Dimension 11) — PASS

RESEARCH.md §"Open Questions" (OQ-01..OQ-05) is structured as resolved verifications, each marked `[VERIFIED: …]` against installed pydantic-ai 0.8.1 source. No unresolved-question section requires the planner's intervention. ✓

### Pattern Compliance (Dimension 12) — PASS

PATTERNS.md analog references are correctly cited in plan tasks: `UserRepository(ABC)` template for `ConversationStore`/`LLMProvider` ABCs (05-02 Tasks 1, 2); `SessionLLMConfig` template for `ChatDeps` (05-02 Task 2); `test_protocol_conformance.py` analog for the renamed `test_protocol_abc.py` (05-01 Task 3); `test_chat_service_flow.py` analog for the rewritten integration test (05-04 Task 4).

## 5. Required Revisions

The following changes are required before execution begins.

**R1 (BLOCKER, addresses A1 + C1):** Revise plan 05-02 Task 1 so that Wave 1's end-state is importable. Two viable options:
- **Option A — preferred (matches anti-pattern lock spirit):** Add a sub-step that updates `backend/app/llm/providers/{ollama,openai,anthropic,lmstudio}.py` to drop the `BoundProvider` import and switch `from app.llm.protocol import LLMProvider, BoundProvider` to `from app.llm.base import LLMProvider`. The existing `bind_tools` body still uses `BoundProvider` as a return type annotation; replace with `Any` (or `Runnable[Any, Any]`) until Wave 2 rewrites the body. This deletes `protocol.py` outright in plan 05-02 (no shim) and aligns with the CONTEXT.md "pure rename + retype, no backwards-compat shim" anti-pattern lock.
- **Option B — fallback:** Keep `protocol.py` as a real module re-exporting BOTH `LLMProvider` and `BoundProvider` (BoundProvider stays a `Protocol` for one wave) until Wave 2 deletes both at once. Update plan 05-02 Task 1 `<done>` to reflect that `BoundProvider` survives Wave 1.

**R2 (HIGH, addresses A2):** Make plan 05-02 Task 3 remove `Settings.ollama_reasoning_model_prefixes` AND simultaneously update `backend/app/llm/factory.py:97` to drop the `reasoning_model_prefixes=...` keyword argument. This pulls one line of plan 05-03 Task 3 forward by one wave, but it's the only way to keep the codebase importable mid-wave. Add `backend/app/llm/factory.py` to plan 05-02's `files_modified` list.

**R3 (MEDIUM, addresses D7):** Add an explicit Wave 2 prerequisite to plan 05-03's `<execution_context>` or threat model: "Before executing this plan, run `cd backend && uv add pydantic-ai>=0.8.1` (the official Pydantic-team package per RESEARCH §Package Legitimacy Audit). The dep removal is plan 05-05; the install precedes Wave 2 imports." Better: split plan 05-05 Task 1 (legitimacy gate) and Task 2 step 1 (`uv add pydantic-ai`) into a Wave 2 prerequisite, with the `uv remove` of langchain* deferred to Wave 4 — that matches the existing source-code ordering and removes the hidden assumption.

**R4 (MEDIUM, addresses F3):** Plan 05-06 Task 1 `<action>` should explicitly handle the create-if-missing case for `.planning/adrs/ADR-007-pydantic-ai.md` (currently it says only "Edit ... Change the header `Status:` line"). Mirror the existing instruction for ADR-001 ("If the file does not exist, create it..."). Confirm the standalone ADR-007 file does not exist today (`find .planning -name 'ADR-*'` returns empty).

## 6. Sign-Off — Operator Decisions Still Pending

- **Plan 05-04 Task 5 (manual UAT against qwen3:4b):** blocking-human checkpoint requiring local Ollama with `qwen3:4b` pulled. Cannot be auto-validated; operator must confirm browser end-to-end smoke per VALIDATION.md §Manual-Only Verifications.
- **Plan 05-05 Task 1 (package legitimacy gate):** blocking-human checkpoint requiring PyPI metadata cross-check + slopcheck verdict for `pydantic-ai`. RESEARCH §Package Legitimacy Audit pre-confirms `[OK]`, but the gate is policy-mandated and never auto-approvable.
- **(Implicit) D-13 gated cloud acceptance tests:** require `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / live Ollama daemon. Plans correctly mark these `pytest.mark.skipif` and they will skip in default CI.


## 7. Second-Pass Verdict (after revisions)

**Verdict:** PASS (with 2 documentary WARNINGs in plan 05-04 — non-blocking)

### Revision Application Status

| Revision | Description | Status | Evidence |
|----------|-------------|--------|----------|
| R1 | Wave 1 ImportError fix — protocol.py deleted outright; provider imports retyped to `from app.llm.base import LLMProvider`; `bind_tools` annotation `BoundProvider` → `Any` | ✓ | 05-02-PLAN.md:179–184 (`<behavior>`), 05-02-PLAN.md:189–195 (`<action>` migrates four providers in same task), 05-02-PLAN.md:204 (`<verify>` chains `grep -rEn "BoundProvider"` + import-smoke `python -c "from app.llm.providers import ollama, openai, anthropic, lmstudio"` + `test ! -f backend/app/llm/protocol.py`). Files added to frontmatter: 05-02-PLAN.md:17–20 (all four provider files in `files_modified:`). Plan 05-03 stale "delete protocol.py" claims removed: 05-03-PLAN.md:30 ("`app/llm/protocol.py` was already deleted in Wave 1") + 05-03-PLAN.md:309, 317, 323 ("DO NOT re-edit"). |
| R2 | Settings/factory sync — Settings field removal + factory call-site edit in same Wave-1 task | ✓ | 05-02-PLAN.md:294 (`<behavior>` line: "factory.py's OllamaProvider(...) construction call no longer passes reasoning_model_prefixes=..."), 05-02-PLAN.md:309 (`<action>`: "Edit backend/app/llm/factory.py IN THE SAME TASK ... DROP the `reasoning_model_prefixes=...` keyword argument"). `backend/app/llm/factory.py` added to plan 05-02 `files_modified:` at 05-02-PLAN.md:16. Plan 05-03 explicitly states "DO NOT re-edit" the factory line (05-03-PLAN.md:313, 323). |
| R3 | pydantic-ai install moved to Wave 2 — Task 0 (legitimacy gate) + Task 0b (`uv add`) added to plan 05-03; corresponding task removed from plan 05-05 | ✓ | Plan 05-03: Task 0 (`checkpoint:human-verify`) at 05-03-PLAN.md:135–153; Task 0b (`auto`) at 05-03-PLAN.md:155–181 with own `<verify><automated>`. Plan 05-05: old Task 1 (legitimacy gate) is gone — current Task 1 at 05-05-PLAN.md:63 is now "Remove langchain* + langgraph and bump pydantic floor"; current Task 2 is the check sweep. `must_haves.truths` of 05-05 explicitly states pydantic-ai was already added in Wave 2 (05-05-PLAN.md:18, 21). Plan 05-05 Task 1 `<action>` at 05-05-PLAN.md:79 says "DO NOT re-run" the legitimacy gate or `uv add 'pydantic-ai>=0.8.1'`. Wave 4 still depends on Wave 3 (05-05-PLAN.md:7). |
| R4 | ADR-007 create-if-missing — plan 05-06 Task 1 mirrors ADR-001 instruction | ✓ | 05-06-PLAN.md:99 (`<action>`: "if `.planning/adrs/ADR-007-pydantic-ai.md` does not exist, CREATE it with the standard ADR header"); 05-06-PLAN.md:123 (`<verify><automated>` chains `test -f .planning/adrs/ADR-007-pydantic-ai.md && ... && grep -q "Status: Locked" .planning/adrs/ADR-007-pydantic-ai.md`). Confirmed via `ls .planning/adrs/` that the file does not exist today, so the create-if-missing branch is the live path. |

### Cross-cutting checks

- **Requirements coverage:** `REQ-pydantic-ai-migration` appears in all six plans' `requirements:`; `REQ-p5-stream-event-abc` appears in 05-01 and 05-02 (the latter delivers it via Task 3). ✓
- **Wave dependency chain:** 05-01 (Wave 0, no deps) → 05-02 (Wave 1, ["05-01"]) → 05-03 (Wave 2, ["05-02"]) → 05-04 (Wave 3, ["05-03"]) → 05-05 (Wave 4, ["05-04"]) → 05-06 (Wave 5, ["05-05"]). No cycles, no forward references. ✓
- **Sampling density:** Plan 05-03 now has 5 tasks (Task 0 checkpoint + Task 0b auto + Tasks 1–3 auto+tdd). 4 of 5 tasks carry `<automated>` verify; the lone non-verifying task is the human checkpoint, which is followed immediately by Task 0b's verify. No window of 3 consecutive tasks lacks an automated verify across the full phase ordering. ✓
- **D-XX coverage:** All 21 decisions still mapped to at least one task (verified by re-reading the new Task 0/0b in 05-03 — these new tasks specifically deliver D-20's `pydantic-ai` add half ahead of schedule). ✓

### Findings

**WARNING W1 — plan 05-04, line 283 (`<action>`).** The fixture-rewrite action says: `from app.llm.protocol import BoundProvider (deleted in Wave 2)`. After R1, `protocol.py` is deleted in **Wave 1** (Plan 05-02 Task 1), not Wave 2. The instruction itself is correct ("drop the import"); only the parenthetical attribution is stale. Non-blocking. Fix: change "deleted in Wave 2" → "deleted in Wave 1" at 05-04-PLAN.md:283.

**WARNING W2 — plan 05-04, line 395 (threat model T-05.4-SC).** The threat-model entry says: "`pydantic-ai` legitimacy checked in plan 05-05 Wave 4". After R3, the legitimacy gate is in plan **05-03 Task 0** (Wave 2). The mitigation correctly notes the package "is already installed for the import path to succeed" — which is true precisely *because* R3 moved the install forward — but the cross-reference is stale. Non-blocking. Fix: change "plan 05-05 Wave 4" → "plan 05-03 Wave 2 (Task 0)" at 05-04-PLAN.md:395.

Neither finding affects execution outcomes (the `<action>` and `<verify>` paths are correct; only documentary parentheticals are stale). They are flagged as WARNING per the policy that documentary drift between plans erodes future readers' trust.

### Sign-off

- All required revisions applied: **yes** (R1 ✓, R2 ✓, R3 ✓, R4 ✓).
- Plan set ready for `/gsd:execute-phase`: **yes** — the two warnings above are documentary cross-reference drift in plan 05-04 prose that do not gate execution. The executor should fix W1 and W2 in passing if they read those lines, but no behavior changes if they do not.
