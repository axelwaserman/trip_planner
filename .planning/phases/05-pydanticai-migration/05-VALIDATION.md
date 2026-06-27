---
phase: 5
slug: pydanticai-migration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-03
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (backend), Vitest (frontend — unchanged in this phase) |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd backend && uv run pytest tests/unit -x` |
| **Full suite command** | `just test` (unit + integration + e2e via path discovery) |
| **Estimated runtime** | ~30s quick / ~3 min full (offline; e2e gated) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/unit -x`
- **After every plan wave:** Run `just test-unit && just test-integration` (offline, fast)
- **Before `/gsd:verify-work`:** `just test` + `just check` must be green
- **Max feedback latency:** 60 seconds for unit, 180 seconds for full offline suite

---

## Per-Task Verification Map

> The planner fills this in. The list below is the **minimum sampling skeleton** the plan-checker will measure against — every line maps to a Phase 5 success criterion or a locked decision (D-XX) from CONTEXT.md.

| Coverage Area | Source Decision | Test Type | Automated Command | File Exists | Status |
|---|---|---|---|---|---|
| `LLMProvider(ABC)` — single tier, no `BoundProvider` | D-01, D-02, D-03 | unit | `uv run pytest tests/unit/llm/test_protocol_abc.py -v` | ❌ W0 | ⬜ pending |
| `LLMProviderFactory.build()` returns concrete `LLMProvider` | D-04 | unit | `uv run pytest tests/unit/llm/test_factory.py -v` | ✅ | ⬜ pending |
| `ChatDeps` frozen dataclass shape | D-05 | unit | `uv run pytest tests/unit/chat/test_deps.py -v` | ❌ W0 | ⬜ pending |
| `search_flights(ctx: RunContext[ChatDeps], ...)` reads `ctx.deps.flight_client` | D-06 | unit | `uv run pytest tests/unit/tools/test_flight_search.py -v` | ✅ | ⬜ pending |
| `search_flights._flight_client` back-door is removed | D-06 (anti-pattern) | unit | `uv run pytest tests/unit/tools/test_flight_search_no_backdoor.py -v` | ❌ W0 | ⬜ pending |
| `provider.build_agent(tools, deps_type)` constructs `Agent[ChatDeps, str]` | D-07 | unit | `uv run pytest tests/unit/llm/test_build_agent.py -v` | ❌ W0 | ⬜ pending |
| `ConversationStore(ABC)` + `InMemoryConversationStore` round-trip | D-08, D-11 | unit | `uv run pytest tests/unit/chat/test_conversation_store.py -v` | ❌ W0 | ⬜ pending |
| `ChatService._agents: dict[str, Agent[ChatDeps, str]]` lifecycle | D-10 | unit | `uv run pytest tests/unit/chat/test_chat_service.py::test_agents_lifecycle -v` | ✅ (rewrite) | ⬜ pending |
| `agent.iter()` event loop maps `ThinkingPart`/`Delta` → `ThinkingEvent` | D-12, RESEARCH OQ-02 | unit | `uv run pytest tests/unit/chat/test_stream_event_extraction.py::test_thinking -v` | ❌ W0 | ⬜ pending |
| `agent.iter()` event loop maps `TextPart`/`Delta` → `ContentEvent` | D-12, RESEARCH OQ-02 | unit | `uv run pytest tests/unit/chat/test_stream_event_extraction.py::test_text -v` | ❌ W0 | ⬜ pending |
| `agent.iter()` event loop maps `FunctionToolCallEvent` → `ToolCallEvent` | RESEARCH §3 streaming arch | unit | `uv run pytest tests/unit/chat/test_stream_event_extraction.py::test_tool_call -v` | ❌ W0 | ⬜ pending |
| `agent.iter()` event loop maps `FunctionToolResultEvent` → `ToolResultEvent` | RESEARCH §3 streaming arch | unit | `uv run pytest tests/unit/chat/test_stream_event_extraction.py::test_tool_result -v` | ❌ W0 | ⬜ pending |
| Exception in stream → `ErrorEvent` (with `_scrub`) | D-12 + Phase 4.7 contract | unit | `uv run pytest tests/unit/chat/test_stream_error_event.py -v` | ❌ W0 | ⬜ pending |
| `OpenAIResponsesModel` dispatch for o-series | D-14, RESEARCH OQ-03 | unit | `uv run pytest tests/unit/llm/providers/test_openai_dispatch.py -v` | ❌ W0 | ⬜ pending |
| Ollama provider via `OpenAIChatModel(base_url=...)` | RESEARCH §3 per-provider | unit | `uv run pytest tests/unit/llm/providers/test_ollama.py -v` | ✅ (rewrite) | ⬜ pending |
| Anthropic provider with extended thinking surface | RESEARCH §3 per-provider | unit | `uv run pytest tests/unit/llm/providers/test_anthropic.py -v` | ✅ (rewrite) | ⬜ pending |
| LM Studio provider — `api_key` sentinel handling per RESEARCH | RESEARCH §3 per-provider | unit | `uv run pytest tests/unit/llm/providers/test_lmstudio.py -v` | ✅ (rewrite) | ⬜ pending |
| `qwen3` `<think>` tags parse natively into `ThinkingPart` | D-12, RESEARCH OQ-04 | unit | `uv run pytest tests/unit/llm/providers/test_ollama_thinking.py -v` | ❌ W0 | ⬜ pending |
| `StreamEvent(BaseModel, ABC)` + `Field(discriminator='type')` golden test | D-15, D-16, RESEARCH OQ-01 | unit | `uv run pytest tests/unit/chat/test_stream_event_abc.py -v` | ❌ W0 | ⬜ pending |
| SSE wire format (`model_dump_json()`) byte-equivalent to Phase 4.7 | D-15 backward-compat | unit | `uv run pytest tests/unit/chat/test_stream_event_wire_compat.py -v` | ❌ W0 | ⬜ pending |
| `MockLLMStream` 3 locked scenarios (`greeting`, `single_tool_call`, `multi_turn`) | D-17, D-18, D-19 | integration | `uv run pytest tests/integration/test_chat_stream.py -v` | ✅ (rewrite) | ⬜ pending |
| `make_chat_service_with_mock_llm()` factory signature unchanged | D-18 | integration | `uv run pytest tests/integration/test_chat_factory.py -v` | ✅ (rewrite) | ⬜ pending |
| `langchain*` packages absent from `pyproject.toml`; `pydantic-ai` present | D-20 | unit | `uv run pytest tests/unit/test_dependencies.py -v` | ❌ W0 | ⬜ pending |
| `langgraph` removed (RESEARCH cleanup) | RESEARCH §0 cleanup | unit | covered by `test_dependencies.py` | ❌ W0 | ⬜ pending |
| `default pytest` stays fast and offline (no real LLM) | D-19 | meta | `cd backend && uv run pytest tests/unit tests/integration -x` (must pass with no `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` set) | ✅ | ⬜ pending |
| Per-provider gated reasoning acceptance test (Ollama qwen3) | D-13 | gated-acceptance | `OLLAMA_BASE_URL=http://localhost:11434 uv run pytest tests/integration/llm/test_ollama_thinking_live.py -v` | ❌ W0 | ⬜ pending |
| Per-provider gated reasoning acceptance test (OpenAI o-series) | D-13 | gated-acceptance | `OPENAI_API_KEY=... uv run pytest tests/integration/llm/test_openai_thinking_live.py -v` | ❌ W0 | ⬜ pending |
| Per-provider gated reasoning acceptance test (Anthropic claude-3-7-sonnet) | D-13 | gated-acceptance | `ANTHROPIC_API_KEY=... uv run pytest tests/integration/llm/test_anthropic_thinking_live.py -v` | ❌ W0 | ⬜ pending |
| ADR-001 → Superseded; ADR-007 → Locked; ARCHITECTURE.md updated | D-21 | docs | `grep -q "Status: Superseded" .planning/adrs/ADR-001*.md && grep -q "Status: Locked" .planning/adrs/ADR-007*.md` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling-density rule:** No 3 consecutive plan tasks may ship without at least one row above marked green. The plan-checker enforces this against the eventual `<automated>` blocks in PLAN.md.

---

## Wave 0 Requirements

- [ ] `backend/tests/unit/llm/test_protocol_abc.py` — assert `LLMProvider` is `ABC` (not `Protocol`); `BoundProvider` removed
- [ ] `backend/tests/unit/llm/test_build_agent.py` — assert every concrete provider's `build_agent(tools, deps_type)` returns a `pydantic_ai.Agent`
- [ ] `backend/tests/unit/llm/providers/test_openai_dispatch.py` — assert `o3-mini`/`o1-mini` route to `OpenAIResponsesModel`; `gpt-4o-mini` routes to `OpenAIChatModel`
- [ ] `backend/tests/unit/llm/providers/test_ollama_thinking.py` — assert `qwen3` `<think>` tag chunks surface as `ThinkingPart` from PydanticAI
- [ ] `backend/tests/unit/chat/test_deps.py` — assert `ChatDeps` is `@dataclass(frozen=True)` and shape matches D-05
- [ ] `backend/tests/unit/chat/test_conversation_store.py` — `InMemoryConversationStore` round-trip for `append`/`load`/`delete`/`list_for_user`; uses `list[ModelMessage]` natively (D-11)
- [ ] `backend/tests/unit/chat/test_stream_event_abc.py` — `isinstance(ContentEvent(...), StreamEvent)` and `Field(discriminator='type')` round-trip via `TypeAdapter` (RESEARCH §5)
- [ ] `backend/tests/unit/chat/test_stream_event_wire_compat.py` — golden file: byte-equivalent `model_dump_json()` of all 5 events vs Phase 4.7 reference
- [ ] `backend/tests/unit/chat/test_stream_event_extraction.py` — drives the `agent.iter()` loop with `FunctionModel` and asserts the `ContentEvent`/`ThinkingEvent`/`ToolCallEvent`/`ToolResultEvent` mapping
- [ ] `backend/tests/unit/chat/test_stream_error_event.py` — exception in stream surfaces as `ErrorEvent` with `_scrub` applied
- [ ] `backend/tests/unit/tools/test_flight_search_no_backdoor.py` — `search_flights._flight_client` AttributeError; signature has `ctx: RunContext[ChatDeps]` first
- [ ] `backend/tests/unit/test_dependencies.py` — `pyproject.toml` has no `langchain*` and no `langgraph`; has `pydantic-ai`
- [ ] `backend/tests/fixtures/llm.py` — full rewrite using PydanticAI `FunctionModel` per RESEARCH §6 (preserves `make_chat_service_with_mock_llm` signature per D-18)
- [ ] `backend/tests/integration/test_chat_stream.py` — three locked scenarios via the new fixture (D-19)
- [ ] `backend/tests/integration/llm/test_{ollama,openai,anthropic}_thinking_live.py` — gated acceptance tests skeleton with `pytest.mark.skipif(env_not_set, ...)` (D-13)

*If existing infra covers a row above, drop the W0 stub for it. Frontend tests are unchanged: SSE wire is byte-equivalent (`StreamEvent.model_dump_json()`).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser end-to-end smoke: streaming chat with tool call against a real Ollama qwen3 | REQ-pydantic-ai-migration | Live LLM + browser SSE rendering can't be asserted offline; Phase 4.7 frontend must continue rendering `ThinkingCard` and `ToolExecutionCard` unchanged | (1) `just backend && just frontend`; (2) start Ollama with `qwen3:4b`; (3) open `http://localhost:5173`; (4) send "find flights JFK→LAX 2026-07-15"; (5) confirm `ThinkingCard` renders, `ToolExecutionCard` shows `search_flights` call+result, final assistant message renders |
| ADR-001 / ADR-007 wording reads correctly post-transition | D-21 | Prose change; mechanical test only checks status header | Read `.planning/adrs/ADR-001-langchain.md` and `.planning/adrs/ADR-007-pydantic-ai.md` and confirm transition narrative is consistent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references in the per-task table
- [ ] No watch-mode flags in any test command
- [ ] Feedback latency < 60s for unit slice, < 180s for full offline suite
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
