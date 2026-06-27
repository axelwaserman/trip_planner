# ADR-001: LangChain 1.0 with bind_tools() Pattern

**Date**: 2025-11-10
**Status**: Superseded by ADR-007 (Phase 5, 2026-06-03)

<!-- Plain-text mirror for grep-based verification: -->
<!-- Status: Superseded by ADR-007 -->


## Context

Need agent framework for tool calling with LLMs.

## Decision

Use LangChain 1.0 `bind_tools()` pattern instead of older `create_agent()` approach.

## Rationale

- LangChain 1.0 uses LangGraph under the hood (more flexible)
- `bind_tools()` works with any chat model that supports function calling
- Simpler pattern: just bind tools to LLM, no separate agent object
- Easier to test (mock LLM directly)

## Consequences

- Cleaner code, less abstraction
- Works with streaming out of the box
- Easy to switch LLM providers
- Less guidance on agent patterns (more DIY)
- Two-tier `LLMProvider → BoundProvider` shape required because `bind_tools`
  returns `Runnable`, not `BaseChatModel` (Phase 4.5 rationale).
- `LLMProvider` and `BoundProvider` were defined as `typing.Protocol` rather
  than `abc.ABC`, in tension with the project rule documented in `CLAUDE.md`
  (carried as "Known Tech Debt" in `ARCHITECTURE.md` through Phase 4.x).
- Tool dependency injection required a `search_flights._flight_client`
  attribute back-door (carried as "Monkey-Patched Tool Dependency" anti-pattern
  in `ARCHITECTURE.md`).

## Supersession Note

LangChain was superseded by **PydanticAI** in Phase 5 (2026-06-03). Per
`.planning/phases/05-pydanticai-migration/05-CONTEXT.md` D-01..D-21, PydanticAI
is lighter, easier to test, exposes a single-tier provider abstraction
(PydanticAI's `Agent` IS the tool-bound thing), provides native tool
dependency injection via `RunContext[Deps]`, parses `<think>` tags into
`ThinkingPart` natively (no `chunk.additional_kwargs["reasoning_content"]`
indirection), and fits the project's ABC convention without the Protocol-vs-ABC
tech-debt entry.

The migration replaced:

| Phase 4.x (LangChain) | Phase 5 (PydanticAI) |
|-----------------------|----------------------|
| `provider.bind_tools(tools)` → `BoundProvider` | `provider.build_agent(tools, deps_type)` → `Agent[Deps, str]` |
| `chunk.additional_kwargs["reasoning_content"]` | `ThinkingPartDelta.content_delta` |
| `@tool` decorator + `search_flights._flight_client = ...` | Plain `async def` with `ctx: RunContext[ChatDeps]` first param |
| `LLMProvider`/`BoundProvider` `typing.Protocol` | Single `LLMProvider(ABC)` |
| `InMemoryChatMessageHistory` per session | `list[ModelMessage]` in `ConversationStore(ABC)` |

**Pointers:**
- Locked decision: `.planning/phases/05-pydanticai-migration/05-CONTEXT.md` (D-21)
- Superseding ADR: `.planning/adrs/ADR-007-pydantic-ai.md`
- Migration date: 2026-06-03
