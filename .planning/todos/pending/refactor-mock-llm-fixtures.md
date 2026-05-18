---
title: Abstract MockLLM fixture into a reusable scenario-builder API
created: 2026-05-18
source: PR #15 review (axelwaserman, 2026-05-18)
priority: medium
type: refactor
---

## Why

`MockLLM` in `tests/fixtures/llm.py` is growing: it already handles
multi-turn tool-call sequences and StopIteration guards. As more complex
tool-calling scenarios land, individual test files will start duplicating
canned response construction logic. A scenario-builder API centralises that
and keeps tests readable.

## What

1. Design a `ScenarioBuilder` (or similar) fluent API in
   `tests/fixtures/llm.py` that lets callers compose multi-turn sequences
   declaratively:
   ```python
   llm = (
       MockLLMBuilder()
       .then_tool_call("search_flights", {...})
       .then_content("Here are your results")
       .build()
   )
   ```
2. Move any per-test fixture initialisation that duplicates response
   construction out of individual test files and into shared factory helpers.
3. Ensure `MockLLM` remains a plain `BaseChatModel` subclass so it can be
   injected anywhere a real LLM is expected without test-framework leakage.

## Trigger

When a second test file needs to construct a non-trivial multi-turn
tool-calling sequence — that's the signal to do this refactor.

## Acceptance criteria

- [ ] No canned response construction logic duplicated across test files
- [ ] `just test` passes with no behaviour changes
- [ ] `MockLLM` still injectable as `BaseChatModel`
