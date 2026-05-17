# Phase 04.5 — Deferred Items (out-of-scope discoveries during execution)

## TC001 in backend/app/chat.py:25

`from app.llm.protocol import BoundProvider` is currently imported at runtime
but ruff's `flake8-type-checking` rule (TC001) flags it as a type-only import
that should move into a `TYPE_CHECKING` block. Discovered during Plan 02b
execution while running `just check`.

* Pre-existing — introduced by Plan 06 commit `52a34a7` (`refactor(04.5-06):
  rewire ChatService around LLMProviderFactory + per-session bound providers`).
* Out of scope for Plan 02b (touched files: log_scrubbing.py, log_scrubbing tests,
  api/main.py, app/llm/__init__.py).
* Resolution: a follow-up plan (likely 04.5-04b/04.5-07 or a Plan 06 hotfix)
  should move the import into a `if TYPE_CHECKING:` block. Trivial fix; no
  behavior change.
