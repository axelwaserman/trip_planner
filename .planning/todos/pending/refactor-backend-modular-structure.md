---
title: Refactor backend/app into per-domain modular structure
created: 2026-05-16
source: PR #7 review (axelwaserman, 2026-05-16)
priority: medium
type: refactor
---

## Why

The current `backend/app/` flat-ish layout (`api/routes/`, `services/`,
`models.py`, `tools/`) is workable but mixes concerns at one level. As the
phase count grows, per-domain modules will keep cohesion high and let new
features land without cross-touching unrelated files.

## Target structure

```
backend/app/
├── main.py
├── config.py
├── database.py             # when persistence lands
├── auth/
│   ├── models.py
│   ├── schemas.py
│   ├── routes.py
│   ├── services.py
│   └── utils.py
├── chat/                   # current ChatService + routes/chat-related models
│   ├── models.py
│   ├── schemas.py
│   ├── routes.py
│   └── services.py
├── providers/              # provider_probe + any future provider wiring
│   ├── schemas.py
│   ├── routes.py           # /api/providers
│   └── services.py         # probe_provider, ProbeErrorCode
├── tools/                  # search_flights and friends — already domain-shaped
│   └── flights/
│       ├── client.py
│       ├── search.py
│       └── models.py
└── shared/
    ├── dependencies.py
    └── exceptions.py
```

## Steps

1. Create the new sub-packages with `__init__.py` re-exports so existing
   imports keep working during the move.
2. Move files one domain at a time (`auth/` first, then `providers/`, then
   `chat/`). Each domain ships as its own atomic commit.
3. Update routers in `main.py` to register from the new locations.
4. Delete the legacy paths once all imports are migrated.
5. Update `CLAUDE.md` Architecture section + `ARCHITECTURE.md` accordingly.

## Out of scope

- No business logic changes.
- No public-API changes (`/api/auth/*`, `/api/chat/*`, `/api/providers` stay
  identical).

## Acceptance criteria

- [ ] `just check` and `just test` pass after each domain move
- [ ] No file in `backend/app/` exceeds 800 lines after the refactor
- [ ] CLAUDE.md and ARCHITECTURE.md describe the new layout
