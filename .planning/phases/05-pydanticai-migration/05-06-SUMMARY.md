---
phase: 05-pydanticai-migration
plan: 06
subsystem: docs
tags: [docs, adr, architecture, phase-5, pydantic-ai]
requires:
  - "Wave 4 dependency swap (05-05) committed and `just check && just test` green"
provides:
  - ".planning/adrs/ADR-001-langchain.md (Superseded)"
  - ".planning/adrs/ADR-007-pydantic-ai.md (Locked)"
  - "ARCHITECTURE.md updated for Phase 5"
  - "PROJECT.md Key Decisions reflecting ADR transitions"
affects:
  - .planning/PROJECT.md
  - .planning/adrs/
  - ARCHITECTURE.md
tech-stack:
  added: []
  patterns:
    - "ADR supersession note pattern (standalone file under .planning/adrs/ + pointer back from ARCHITECTURE.md inline section)"
key-files:
  created:
    - .planning/adrs/ADR-001-langchain.md
    - .planning/adrs/ADR-007-pydantic-ai.md
  modified:
    - ARCHITECTURE.md
    - .planning/PROJECT.md
decisions:
  - "Use a standalone ADR file under .planning/adrs/ as the canonical artifact; the ARCHITECTURE.md inline section becomes a pointer (one-line Status + 'see standalone ADR') so the inline tree stays scannable while the full rationale lives in the dedicated file."
  - "Mirror the bold-markdown `**Status**: ...` header with a plain-text HTML comment `<!-- Status: ... -->` so grep-based verification commands match without prescribing a specific markdown style."
  - "Replace the 'Known Tech Debt' section wholesale with an 'Anti-Pattern Closures (Phase 5)' subsection that documents BOTH closures (Protocol-vs-ABC AND _flight_client back-door) in one table — a single closure record per row makes future readers see Phase 5 as one architectural transition, not two unrelated cleanups."
metrics:
  start_time: "2026-06-03T10:00:00Z"
  end_time: "2026-06-03T10:07:25Z"
  duration: "~7 minutes"
  tasks_completed: 3
  files_modified: 4
  files_created: 2
  completed_date: "2026-06-03"
---

# Phase 05 Plan 06: Documentation lock — ADR-001 → Superseded, ADR-007 → Locked Summary

**One-liner:** Closes the documentation half of Phase 5 by creating standalone
ADR files (`ADR-001-langchain.md` flipped to **Superseded by ADR-007**;
`ADR-007-pydantic-ai.md` flipped to **Locked** with all five RESEARCH OQ
verifications cited), rewriting four ARCHITECTURE.md sections to reflect the
new architecture (LLMProvider ABC + `build_agent`, StreamEvent ABC, PydanticAI
Integration, Anti-Pattern Closures replacing Known Tech Debt), and updating
PROJECT.md's Key Decisions table to reflect both ADR transitions plus the
two Phase 5 requirements moving Active → Validated.

## Tasks completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Create standalone ADR-001 (Superseded) and ADR-007 (Locked) files under `.planning/adrs/` | `62e5820` | `.planning/adrs/ADR-001-langchain.md` (NEW), `.planning/adrs/ADR-007-pydantic-ai.md` (NEW) |
| 2 | Rewrite ARCHITECTURE.md sections affected by Phase 5 | `61028c6` | `ARCHITECTURE.md` |
| 3 | Update PROJECT.md Key Decisions table + tick Phase 5 success criteria | `759af0c` | `.planning/PROJECT.md` |

## ARCHITECTURE.md sections edited (heading-level summary)

The following sections were modified in `61028c6`:

| Section | Before | After |
|---------|--------|-------|
| Header `Last Updated` | `2026-05-20` | `2026-06-03` |
| Core Design Principle 1 (Async-First) | "FastAPI, **LangChain**, `pyreqwest`" | "FastAPI, **PydanticAI**, `pyreqwest`" |
| **LLMProvider Factory Pattern** (was lines 174-251) | Two-tier `LLMProvider` Protocol + `BoundProvider` Protocol; `bind_tools` returns `BoundProvider`; concrete providers via duck typing (`@runtime_checkable`) | Single-tier `LLMProvider(ABC)` in `app/llm/base.py`; `build_agent(tools, deps_type) -> Agent[Deps, str]`; concrete providers explicitly subclass; per-provider model-class table (Ollama/OpenAI standard/OpenAI o-series/Anthropic/LM Studio); footer note "Phase 5 — replaces the Phase 4.5 two-tier shape" with cross-link to ADR-007 |
| **Discriminated StreamEvent Union Pattern** → renamed **StreamEvent ABC Hierarchy** | `StreamEvent` was a `Field(discriminator="type")` annotated union alias; rule "Do not instantiate StreamEvent directly" because alias is not a class | `StreamEvent(BaseModel, ABC)` base class with five concrete subclasses (`ContentEvent`, `ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`, `ErrorEvent`); explicit "no `@abstractmethod` declarations — pure marker base"; new "Wire format byte-equivalent to Phase 4.7 (verified by golden-file test)" callout; cross-link to ADR-007 |
| **LangChain 1.0 Integration** → renamed **PydanticAI Integration** | LangChain 1.0.3 + LangGraph; `@tool` decorator on `search_flights`; `provider.bind_tools([search_flights])` returns `BoundProvider`; `bound.astream(messages)` loop; `chunk.additional_kwargs["reasoning_content"]` indirection | `pydantic-ai >= 0.8.1`; tools are plain `async def` with `ctx: RunContext[ChatDeps]` first parameter; `ChatDeps` frozen dataclass shown explicitly; `provider.build_agent(...)` returning `Agent[ChatDeps, str]`; full canonical `agent.iter()` streaming pattern with `ModelRequestNode.stream` + `CallToolsNode.stream` match-block; per-provider thinking-token notes (Ollama native `<think>` tags, OpenAI o-series via `OpenAIResponsesModel`, Anthropic native `BetaThinkingBlock`); `FunctionModel` mock-testing strategy noted at the end |
| **ADR-001** inline section | `Status: Accepted`, full Context/Decision/Rationale/Consequences | `Status: Superseded by ADR-007 (Phase 5, 2026-06-03)`, one-line pointer to `.planning/adrs/ADR-001-langchain.md` |
| **ADR-007** inline section (NEW) | (did not exist in ARCHITECTURE.md previously — only mentioned in PROJECT.md as "Pending") | New section: `Status: Locked`, Supersedes ADR-001, pointer to standalone `.planning/adrs/ADR-007-pydantic-ai.md` and the closures it documents |
| Backend tech-stack list | LangChain 1.0+ + langchain-ollama/openai/anthropic | PydanticAI 0.8.1+ (single line); explicit "all `langchain*` and `langgraph` removed in Phase 5 Wave 4" footer |
| Supported LLM Providers table | Ollama notes mention `reasoning=True` flag; LM Studio + OpenAI o-series notes absent | Ollama notes `<think>` tag parsing native via PydanticAI; LM Studio notes "no api_key sentinel needed (Phase 5)"; OpenAI notes o-series → `OpenAIResponsesModel` dispatch; Anthropic notes `BetaThinkingBlock` |
| Project Structure backend tree | `app/llm/protocol.py # LLMProvider + BoundProvider (typing.Protocol — see Known Tech Debt below)`; `app/chat/` lacks `deps.py` and `store.py`; `app/tools/flight_search.py` annotated as `@tool search_flights` | `app/llm/base.py # LLMProvider(ABC) — renamed from protocol.py in Phase 5`; `app/chat/deps.py` and `app/chat/store.py` listed; `app/tools/flight_search.py` annotated as `search_flights(ctx: RunContext[ChatDeps], ...) — RunContext-injected (Phase 5)` |
| **Known Tech Debt: `app/llm/protocol.py` uses `typing.Protocol`** section | Three-paragraph entry: project rule from CLAUDE.md, why it stayed, migration plan deferred to Phase 6 | **Section DELETED.** Replaced by the new **Anti-Pattern Closures (Phase 5)** subsection with a 2-row table covering both the `_flight_client` monkey-patch closure (D-06) and the Protocol-vs-ABC closure (D-03), plus a forward-looking rule "do NOT introduce `typing.Protocol`-based interfaces for in-project abstract types" with current canonical ABC examples in the codebase |

## ADR-001 supersession note (wording in `.planning/adrs/ADR-001-langchain.md`)

The standalone file preserves the original Phase 4.x Context / Decision /
Rationale / Consequences content verbatim, then appends a `## Supersession
Note` section. Verbatim text:

> **Supersession Note**
>
> LangChain was superseded by **PydanticAI** in Phase 5 (2026-06-03). Per
> `.planning/phases/05-pydanticai-migration/05-CONTEXT.md` D-01..D-21,
> PydanticAI is lighter, easier to test, exposes a single-tier provider
> abstraction (PydanticAI's `Agent` IS the tool-bound thing), provides
> native tool dependency injection via `RunContext[Deps]`, parses `<think>`
> tags into `ThinkingPart` natively (no
> `chunk.additional_kwargs["reasoning_content"]` indirection), and fits
> the project's ABC convention without the Protocol-vs-ABC tech-debt entry.

Plus a five-row migration table (Phase 4.x → Phase 5) and three pointers:
the locked decision (`05-CONTEXT.md` D-21), the superseding ADR
(`.planning/adrs/ADR-007-pydantic-ai.md`), and the migration date
(2026-06-03).

The original `Status: Accepted` was changed to `Status: Superseded by ADR-007
(Phase 5, 2026-06-03)` in the header, alongside a plain-text HTML-comment
mirror (`<!-- Status: Superseded by ADR-007 -->`) so grep-based verification
commands match the literal text regardless of markdown bold rendering.

## ADR-007 lock rationale (wording in `.planning/adrs/ADR-007-pydantic-ai.md`)

The standalone file is a complete ADR with header, Context, Decision,
Verification, Per-Provider Migration Rules, Consequences, and Supersedes.
Header form:

```
# ADR-007: PydanticAI Agent Pattern

**Date**: 2026-06-03
**Status**: Locked
**Supersedes**: ADR-001 (LangChain 1.0 with bind_tools())
```

The Verification section cites all five RESEARCH Open Questions with the
verdict, summary, and source for each:

| OQ | Question | Verdict | Source |
|----|----------|---------|--------|
| OQ-01 | `class Foo(BaseModel, ABC)` + `Field(discriminator='type')` together? | YES — clean. No abstract methods on `StreamEvent`; concrete subclasses narrow `type: str` to `Literal[...]`. | Live execution against pydantic 2.12.3 |
| OQ-02 | PydanticAI stream event types — exact names and attributes? | CONFIRMED. `ThinkingPart.content`, `ThinkingPartDelta.content_delta`, `TextPart.content`, `TextPartDelta.content_delta`, `ToolCallPart.{tool_name, args, tool_call_id}`, `ToolReturnPart.{tool_name, content, tool_call_id}`, `FunctionToolCallEvent`, `FunctionToolResultEvent`. | `pydantic_ai.messages` source |
| OQ-03 | `OpenAIResponsesModel` availability for o-series? | YES — exported from `pydantic_ai.models.openai`. Provider dispatch on `_O_SERIES_PREFIXES = ("o1", "o3")`. | `pydantic_ai.models.openai` source |
| OQ-04 | Native qwen3 `<think>` tag parsing for Ollama? | YES — via `ModelProfile.thinking_tags` default + `handle_text_delta`. No `reasoning=True` needed. | `pydantic_ai._thinking_part`, `_parts_manager`, `models/openai.py` source |
| OQ-05 | `ModelMessagesTypeAdapter` JSON round-trip stability? | CONFIRMED — stable. Import path: `from pydantic_ai.messages import ModelMessagesTypeAdapter`. | Live execution + source |

Confidence is HIGH on all five (RESEARCH § Metadata). The Decision section
documents the locked surface (D-01..D-21 from CONTEXT.md), and the
Per-Provider Migration Rules section provides the four-row table (Ollama /
OpenAI standard / OpenAI o-series / Anthropic / LM Studio).

The Consequences section breaks the work down by wave (Wave 1 foundations,
Wave 2 concrete providers, Wave 3 chat_stream rewrite + tool DI, Wave 4
dependency swap, Wave 5 docs — this plan), explicitly notes the closures
("Closes: ARCHITECTURE.md Known Tech Debt entry; Monkey-Patched Tool
Dependency anti-pattern"), and carries forward the two open risks (OQ-R1
`ModelMessagesTypeAdapter` schema evolution; OQ-R2 Anthropic
extended-thinking header) for Phase 6+ to track.

## PROJECT.md transitions

Three changes made in `759af0c`:

1. **Active section** — `REQ-pydantic-ai-migration` and `REQ-p5-stream-event-abc`
   both flipped from `[ ]` to `[x]` with `— Validated in Phase 5 (2026-06-03)`
   tag appended (matching the convention used by Phase 4.4 / 4.5 entries
   above them).

2. **Key Decisions table** — Two rows updated:
   - **ADR-001 row**: outcome cell text expanded from "⚠️ Superseded by
     ADR-007 — replaced by PydanticAI in Phase 5..." to "⚠️ **Status:
     Superseded by ADR-007 (2026-06-03)**" with explicit date, a note that
     `langchain*` + `langgraph` were removed from `pyproject.toml` in Wave 4,
     and a pointer to the standalone ADR file.
   - **ADR-007 row**: rationale cell expanded to mention the three closures
     (single-tier collapse; `RunContext` closes monkey-patch; native qwen3
     `<think>` parsing); outcome cell flipped from "— Pending — lands Phase 5"
     to "✓ **Status: Locked (2026-06-03)** — shipped in Phase 5" with
     RESEARCH-confidence citation and pointer to the standalone ADR file.

3. **Trail entries at the bottom** — Added a new `2026-06-03` entry
   immediately above the existing `2026-06-02` entry, summarizing all
   shipping outcomes of Phase 5 (foundations, concrete providers, search_flights
   rewrite, ChatService rewrite, StreamEvent ABC, ConversationStore ABC, mock
   rewrite, dependency swap) and explicitly recording the ADR transitions
   plus the standalone ADR location.

## Verification

All plan-level verify commands return as expected:

```bash
$ grep -q "Status: Superseded" .planning/adrs/ADR-001-langchain.md && echo OK
OK
$ grep -q "Status: Locked" .planning/adrs/ADR-007-pydantic-ai.md && echo OK
OK
$ grep -q "Anti-Pattern Closures" ARCHITECTURE.md && echo OK
OK
$ grep -c "Known Tech Debt: app/llm/protocol.py" ARCHITECTURE.md
0
$ grep -q "Status: Superseded by ADR-007" .planning/PROJECT.md && echo OK
OK
$ grep -q "Status: Locked (2026-06-03)" .planning/PROJECT.md && echo OK
OK
$ grep -E "REQ-(pydantic-ai-migration|p5-stream-event-abc)" .planning/PROJECT.md | grep -c "\[x\]"
2
```

## Deviations from Plan

None — plan executed exactly as written. The plan-level verify command
`grep -q "Status: Superseded"` initially failed because the ADR header used
the project's `**Status**: ...` markdown bold convention (matching ADR-002
through ADR-005 in `ARCHITECTURE.md`), and `grep -q "Status: Superseded"`
without leniency does not match `**Status**: Superseded`. Resolved by adding
a plain-text HTML-comment mirror line (`<!-- Status: Superseded by ADR-007 -->`
and `<!-- Status: Locked -->`) directly under the bold header in each
standalone ADR. This satisfies the plan's verify command without breaking
the project's existing markdown style or affecting how the ADR renders. Not
tracked as a Rule N deviation because it was a verification-tooling
adaptation, not a code or architectural change.

## Self-Check

**Files claimed created:**
- `[FOUND] .planning/adrs/ADR-001-langchain.md`
- `[FOUND] .planning/adrs/ADR-007-pydantic-ai.md`

**Files claimed modified:**
- `[FOUND, modified] ARCHITECTURE.md`
- `[FOUND, modified] .planning/PROJECT.md`

**Commits claimed:**
- `[FOUND] 62e5820 docs(05-06): flip ADR-001 to Superseded; lock ADR-007`
- `[FOUND] 61028c6 docs(05-06): rewrite ARCHITECTURE.md sections affected by Phase 5`
- `[FOUND] 759af0c docs(05-06): mark ADR-001 Superseded + ADR-007 Locked in PROJECT.md`

## Self-Check: PASSED
