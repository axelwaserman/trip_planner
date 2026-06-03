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
