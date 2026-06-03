# Phase 5 Deferred Items

Items discovered during plan execution that are out of scope for the current plan
but should be tracked for follow-up plans.

## From 05-02 (Wave 1 Foundations)

### Test files broken by `app/llm/protocol.py` deletion

The following test files import from the now-deleted `app.llm.protocol` module
and fail to collect. They are NOT part of Plan 05-02's `<verify>` scope. The
plan's `<done>` paragraph notes that mid-wave breakage of pre-existing tests
that depend on the LangChain shapes is expected; these specific files are owned
by Wave 2 / Wave 3:

| File | Owning wave | Disposition |
|------|-------------|-------------|
| `backend/tests/unit/llm/test_protocol_conformance.py` | Wave 1 (this plan) — superseded by `test_protocol_abc.py` per PATTERNS.md row 40 | Delete in Wave 2/3 cleanup pass; the new ABC test file replaces it functionally. Not deleted in Wave 1 to avoid touching test_chat_service.py / test_chat_stream.py concurrency. |
| `backend/tests/fixtures/llm.py` | Wave 2 / Plan 05-04 (PATTERNS.md row 39) | Full rewrite — drops `MockLLM(BaseChatModel)` / `_MockBoundProvider`; introduces `_MockLLMProvider(LLMProvider)` that builds an `Agent` from a `FunctionModel(stream_function=...)`. |
| `backend/tests/unit/test_chat_service.py` | Wave 3 / Plan 05-05 (ChatService rewrite) | Rewrite alongside `app/chat/service.py`. The current file mocks `BoundProvider` and exercises the LangChain `_bound_providers` cache shape, which retires in Wave 3. |
| `backend/tests/unit/test_chat_stream.py` | Wave 3 / Plan 05-05 | Migrates onto the new `tests/fixtures/llm.py` fixture; replaces `MockLLM` with `FunctionModel`-backed mocks. |

The plan's verify command targets `tests/unit/llm/test_protocol_abc.py` and
the chat-package Wave 0 stubs; those pass. Broader `pytest tests/unit/`
collection failures are documented here and re-evaluated when Wave 2/3 lands.

## From 05-03 (Wave 2 Providers Rewrite)

### `tests/unit/llm/test_build_agent.py` — 4 tests deferred to Wave 3

The Wave 0 RED test passes `[search_flights]` directly to `provider.build_agent(...)`.
After the Wave 2 rewrite, each provider's `build_agent` returns a real
`pydantic_ai.Agent`. PydanticAI's `Agent.__init__` calls `function.__name__`
on each registered tool — but `search_flights` is currently a LangChain
`@tool`-decorated `StructuredTool`, which masks `__name__` and raises
`AttributeError` at Agent-construction time.

| File | Owning wave | Disposition |
|------|-------------|-------------|
| `tests/unit/llm/test_build_agent.py` | Wave 3 / Plan 05-04 (ChatService + tool rewrite) | All 4 tests turn green when `app/tools/flight_search.py` drops `@tool` and gains `ctx: RunContext[ChatDeps]` as the first parameter (PATTERNS.md row 33). The `flight_search.py` rewrite is NOT in Plan 05-03's `<files_modified>`; it ships with the ChatService rewrite that consumes the new tool signature so the dependency edge is atomic. |
| `tests/unit/tools/test_flight_search_no_backdoor.py` | Wave 3 / Plan 05-04 | Anti-pattern lock for the same `flight_search.py` rewrite. Currently fails because `search_flights` is still wrapped in `StructuredTool` (no `inspect.signature` access, no `ctx` first param). |

### `tests/unit/test_chat_service.py` — module-level skip until Wave 3

The Phase 4.5 file mocks `BoundProvider` and exercises the
`_bound_providers` cache shape that retires in Wave 3. To honour the
"no legacy `protocol` shim references anywhere in the tree" regression
guard, this plan skip-decorates the entire module at collection time
(`pytest.skip(..., allow_module_level=True)`) rather than deleting it —
the body is preserved for the Wave 3 rewrite to retarget onto PydanticAI
`Agent` mocks.

### `tests/unit/llm/test_protocol_conformance.py` — DELETED in this plan

Per `deferred-items` from 05-02, this file was tagged for "delete in Wave
2/3 cleanup pass". The deletion landed in Plan 05-03 Task 3 — its
replacement (`test_protocol_abc.py`) already covers the ABC-conformance
assertions for all four concrete providers.
