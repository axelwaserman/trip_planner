# Current Focus: Phase 4.9 Complete — Ready to Plan Phase 5 (PydanticAI Migration)

**Status**: Phase 4.9 (Pre-Phase-5 Prep) complete
**Date**: 2026-06-02
**Next phase**: **Phase 5 — PydanticAI Migration** (resequenced ahead of Postgres per PR #20 review)

---

## What is done

- **v0 Foundation + Mock Demo** (Phases 1–3): shipped 2025-11-06 → 2025-11-14
- **v1 Working Demo** (Phases 4.2–4.8): app unbroken, CI reset, mock LLM in tests, real LLM provider abstraction (cloud + dynamic Ollama), vendor-neutral tool JSON, discriminated StreamEvent hierarchy, Pydantic validators + test hygiene
- **Phase 4.9 Pre-Phase-5 Prep**: models.py split into domain modules, UserRepository protocol extracted, CLAUDE.md skill-routing table added, 6 frontend bugs fixed

The codebase is on clean foundations: `just check` passes, default `pytest` is fast and offline, auth routes decoupled from internals, domain models in `auth/`, `chat/`, `providers/`, `flights/`.

## What is next

**Phase 5: PydanticAI Migration** *(was Phase 6 — promoted ahead of Postgres on 2026-06-02 per PR #20 review)*

Goal: port `ChatService` from LangChain `bind_tools()` to a PydanticAI `Agent` per session, preserving the SSE `StreamEvent` wire contract so the frontend doesn't change. Bundle in:

- Convert `LLMProvider` and `BoundProvider` from `typing.Protocol` to `abc.ABC` (closes the ARCHITECTURE.md "Known Tech Debt" entry).
- Rewire `search_flights._flight_client` attribute injection to PydanticAI's per-agent dependency mechanism.
- Refactor `StreamEvent` discriminated-union alias into a proper `StreamEvent(ABC)` hierarchy (REQ-p5-stream-event-abc — pulled into Phase 5 because the producer is being rewritten anyway).
- Drop `langchain*` deps; add `pydantic-ai`. ADR-001 → Superseded; ADR-007 → Locked.

Start with `/gsd-discuss-phase` before planning. Then activate `/pydantic-ai-agent-builder` and `/dignified-python` for the implementation.

## Why this order (Phase 5 = PydanticAI before Phase 6 = Postgres)

The original sequencing put Postgres first and PydanticAI second. PR #20 review flipped it. Reasons:

1. **Cheaper now than later.** `ChatService.chat_stream()` plus four provider classes is the entire LangChain footprint. The migration cost grows monotonically as more agent logic accretes — doing it before persistence is the cheapest moment.
2. **No more `Message` shape gamble.** The previous plan made Phase 6 (Postgres) build a `Message` SQLModel against LangChain's `BaseChatMessageHistory`, with a forward-migration to PydanticAI's `ModelMessage` deferred. With PydanticAI first, the table is shaped against `ModelMessage` from the start — no migration, no JSON-payload escape hatch.
3. **Folds three reworks into one.** The Protocol→ABC tech debt in `app/llm/protocol.py`, the `bind_tools` retirement, and the `_flight_client` attribute-injection back-door all close in the same change.

## Sequencing risks for Phase 5 (PydanticAI) planning

1. **PydanticAI streaming surface differs from LangChain.** The `chunk.additional_kwargs["reasoning_content"]` extraction in `ChatService` is LangChain-specific. The PydanticAI rewrite is not a verbatim port — confirm during the discuss phase that thinking-token surfacing works on Ollama qwen3 through PydanticAI before locking the plan.
2. **`MockLLMStream` fixture has to be rebuilt.** The Phase 4.4 fixture is shaped against LangChain's chunk types. Default `pytest` must remain fast and offline, so the new fixture has to drive PydanticAI's agent surface end-to-end without reaching for a real model.

## Sequencing risks for Phase 6 (Postgres) planning *(unchanged from before, but the Phase 5↔6 swap removes the headline risk)*

1. ~~LangChain → PydanticAI rework risk on the `Message` table~~ — **resolved by the resequencing.** The table now targets PydanticAI's `ModelMessage` from the start.
2. **User-data migration gap**: Phase 4.2 keeps `AUTH_USERS` env-seed; Phase 6 retires it via a PG bootstrap script. The migration story is unspecified — do existing JWTs invalidate? do passwords carry over? Define this concretely before the Phase 6 plan is locked (suggested: rotate `jwt_secret` at Phase 6 boot; bootstrap script re-seeds usernames + re-hashes passwords from the env, then unsets the var).

## Full detail

- `.planning/STATE.md` — current milestone, blockers, deferred items
- `.planning/ROADMAP.md` — authoritative phase list and success criteria
