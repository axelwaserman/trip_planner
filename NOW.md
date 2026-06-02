# Current Focus: Phase 4.9 Complete — Ready to Plan Phase 5

**Status**: Phase 4.9 (Pre-Phase-5 Prep) complete  
**Date**: 2026-05-20  
**Next phase**: Phase 5 — Postgres + Redis + docker-compose

---

## What is done

- **v0 Foundation + Mock Demo** (Phases 1–3): shipped 2025-11-06 → 2025-11-14
- **v1 Working Demo** (Phases 4.2–4.8): app unbroken, CI reset, mock LLM in tests, real LLM provider abstraction (cloud + dynamic Ollama), vendor-neutral tool JSON, discriminated StreamEvent hierarchy, Pydantic validators + test hygiene
- **Phase 4.9 Pre-Phase-5 Prep**: models.py split into domain modules, UserRepository protocol extracted, CLAUDE.md skill-routing table added, 6 frontend bugs fixed

The codebase is on clean foundations: `just check` passes, default `pytest` is fast and offline, auth routes decoupled from internals, domain models in `auth/`, `chat/`, `providers/`, `flights/`.

## What is next

**Phase 5: Postgres + Redis + docker-compose**

Goal: a single `docker compose up` brings up backend + frontend + Postgres + Redis. In-memory session history and the `AUTH_USERS` env-seed are replaced by PG-backed storage with `psycopg` async + SQLModel ORM.

Start with `/gsd-discuss-phase` before planning — Phase 5 has a required pre-phase spike (verify `postgresql+psycopg://` async URI with SQLModel).

## Sequencing risks for Phase 5 planning

Before locking the Phase 5 plan, review these concerns from STATE.md Blockers:

1. **LangChain → PydanticAI rework risk**: Phase 5 builds PG-backed message history against LangChain's `BaseChatMessageHistory` shape. Phase 6 then swaps the agent runtime to PydanticAI which uses a different `ModelMessage` shape — the `Message` SQLModel will likely need rework. Same risk at the provider layer: Phase 4.5's `LLMProvider` Protocol mirrors LangChain's `BaseChatModel`; PydanticAI is `Agent`-shaped. Consider keeping the `Message` table generic (JSON `payload` column with a discriminator) to reduce Phase 6 migration cost, or revisit whether to swap Phase 6 forward of Phase 5.

2. **User-data migration gap**: Phase 4.2 keeps `AUTH_USERS` env-seed; Phase 5 retires it via a PG bootstrap script. The migration story is unspecified — do existing JWTs invalidate? do passwords carry over? Define this concretely before the Phase 5 plan is locked (suggested: rotate `jwt_secret` at Phase 5 boot; bootstrap script re-seeds usernames + re-hashes passwords from the env, then unsets the var).

## Full detail

- `.planning/STATE.md` — current milestone, blockers, deferred items
- `.planning/ROADMAP.md` — authoritative phase list and success criteria
