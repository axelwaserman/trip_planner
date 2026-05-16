# backend/tests/e2e/

## Purpose

This directory is the placeholder home for end-to-end tests that drive the
running backend over HTTP. As of Phase 4.3 the CI E2E job is required-for-merge
as a symbolic gate (D-04): it must pass on every PR, but it ships zero real
behavioural tests.

## What belongs here

Forward-looking — these are the tests later phases will land here:

- Auth flow against a running backend: `POST /api/auth/token`
  → `GET /api/auth/me` → one chat turn.
- Real travel-API tests gated on a CI-available secret (e.g. `AMADEUS_*`),
  skipped (never failed) when the secret is absent.

## What does NOT belong here

- Tests that call a real LLM (Ollama, OpenAI, Anthropic, …). Chat-layer
  coverage lives in `tests/integration/` with mocks; Phase 4.4 introduces
  `MockLLMStream` for that.
- Tests that need docker-compose / multi-service stacks — deferred to a
  future Phase 5.1 project-level `e2e/` directory peer of `backend/`.

## How to run

```
cd backend && uv run pytest tests/e2e/
```

During the Phase 4.3 symbolic-gate window this directory contains exactly one
no-op placeholder test (`test_placeholder.py`, added by Plan 05) so the
command exits 0 cleanly with one test collected. The placeholder will be
removed once real auth-flow / travel-API E2E tests land.
