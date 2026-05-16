---
title: Research pyreqwest, replace httpx, ship a custom skill
created: 2026-05-16
source: PR #7 review (axelwaserman, 2026-05-16)
priority: medium
type: research+refactor
---

## Why

One of this project's positioning goals is to demonstrate that "fast Python"
exists. `httpx` integrates well with FastAPI but isn't the fastest async HTTP
client available; `pyreqwest` (a Rust-backed client) is faster and aligns with
the messaging.

## What

1. Run `/gsd-research` (or equivalent) against the pyreqwest documentation
   site to capture canonical idioms, async patterns, error taxonomy, and
   timeout/retry semantics.
2. Author a custom `pyreqwest` skill at `.claude/skills/pyreqwest/SKILL.md`
   modelled on the existing `fastapi` and `chakra-ui` skills.
3. Migrate `backend/app/services/provider_probe.py` (and any future outbound
   HTTP) from `httpx` → `pyreqwest`. Keep the `ProbeErrorCode` taxonomy
   stable so the wire contract doesn't break.
4. Update `CLAUDE.md` Constraints section to point new outbound HTTP at
   `pyreqwest` by default.

## Out of scope

- Inbound HTTP (FastAPI / uvicorn / starlette stays as-is).
- Test mocks — `unittest.mock.AsyncMock` against the new client should
  follow the same shape as today.
