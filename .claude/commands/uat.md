---
name: uat
description: Run the Playwright User Acceptance smoke + visual regression suite against a running dev stack. Catches wiring bugs (provider 404s, malformed SSE) and chat-surface visual drift.
argument-hint: "[smoke|visual|all] [--update-baselines]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

<objective>
Drive the chat application end-to-end via real browser + real backend +
real Ollama / LM Studio (any provider listed as `available: true` in
`/api/providers`) and assert two contracts:

1. **SSE smoke pack** — every available local provider/model permutation
   produces at least one non-error frame in the SSE stream within ~90 s.
   The 8b+ tier additionally drives a `tool_call → tool_result → content`
   ordering. This is the harness that would have caught the Ollama `/v1`
   404 (commit `e21a7e3`).

2. **Visual regression** — login page, empty chat surface, and chat-with-
   first-message render at the canonical viewports (320 / 768 / 1440 /
   1280-default). Pixel diff with mask on the streaming text region so
   token sampling doesn't bake into flake.

Use this every time you've touched `app/llm/providers/*`, the SSE wire
contract in `app/chat/models.py`, the front-end chat surface, or the auth
route. Replaces the deferred manual UAT step from Plan 05-04 Task 5.
</objective>

<arguments>
- `smoke` — run only the SSE smoke pack (`frontend/e2e/smoke/`). Fast
  (~30 s for two local providers), no browser pixel work. Use after
  backend / provider edits.
- `visual` — run only the visual regression pack (`frontend/e2e/visual/`).
  Use after frontend / Chakra / theme edits.
- `all` (default) — both packs.
- `--update-baselines` — re-record the visual regression baselines.
  Required after intended UI changes; commit the resulting
  `__screenshots__/` dir.
</arguments>

<prerequisites>
1. Backend running: `just backend` (port 8000).
2. Frontend running: `just frontend` (port 5173). Playwright auto-starts
   it via `webServer` config; if you've already started it manually it
   will be reused.
3. At least one LLM provider available:
   - Ollama: `ollama serve` + `ollama pull qwen3:4b` (and ideally
     `qwen3:8b` for the tool-cycle assertion).
   - LM Studio: load a model + start the server on port 1234.
4. Default test credentials (`admin:admin` from `Settings.auth_users`).
   Override via `TEST_USER` / `TEST_PASSWORD` env vars if your dev
   `AUTH_USERS` differs.
5. Playwright Chromium installed: `cd frontend && npx playwright install
   chromium` (one-off; cached under `~/Library/Caches/ms-playwright/`).
</prerequisites>

<process>
1. Parse the first positional argument from `$ARGUMENTS` (default `all`).
2. Verify backend is up: `curl -fsS http://localhost:8000/health`.
   If it isn't, surface a clear "start `just backend` first" message and
   stop — do NOT auto-start the backend (it's the user's dev process and
   silently spawning another listener is destructive).
3. Run the requested pack via the matching `just` recipe:
   - `smoke` → `just uat-smoke`
   - `visual` → `just uat-visual` (or `just uat-baselines` if
     `--update-baselines`)
   - `all` → `just uat`
4. On failure, surface the Playwright report path
   (`frontend/playwright-report/index.html`) and the `test-results/`
   directory so the user can open the trace viewer:
   `cd frontend && npx playwright show-report`.
5. On success, summarise: which providers exercised, how many frames
   each produced, whether the tool cycle ran.
</process>

<assertions>
- The smoke pack auto-discovers providers from `/api/providers`. Cloud
  providers are skipped unless `PLAYWRIGHT_INCLUDE_CLOUD=1` is set —
  burning paid API tokens by accident on every UAT run is the wrong
  default.
- `tool_call → tool_result → content` is asserted only on qwen3 ≥ 8b
  (or qwen3.5 ≥ 9b). 4b checkpoints are too weak at tool selection to
  use as a hard gate; the ordering test skips when no large model is
  available.
- Visual regression masks `[data-streaming]` regions. If you add a
  streaming-text element, mark it with that data attribute or the
  baseline will flake.
</assertions>

<known_failure_modes>
- `Login failed: 401` — `AUTH_USERS` doesn't include `admin:admin`. Set
  `TEST_USER` / `TEST_PASSWORD` to a configured pair.
- `at least one local provider must be available` (smoke) — Ollama and
  LM Studio are both `available: false` in `/api/providers`. Start one.
- `status_code: 404 ... body: 404 page not found` (SSE error frame) —
  Ollama base_url misconfigured. Should be either bare
  `http://localhost:11434` (provider appends `/v1`) or include `/v1`
  explicitly. Both are accepted; anything else is broken.
- `toHaveScreenshot` diff > 2% — UI changed. Either revert, or run
  `--update-baselines` and commit the new `__screenshots__/` images.
</known_failure_modes>

<files_to_read>
- `frontend/playwright.config.ts` — projects, viewports, webServer.
- `frontend/e2e/lib/api.ts` — backend HTTP helpers, SSE frame parser.
- `frontend/e2e/smoke/sse-providers.spec.ts` — the smoke pack.
- `frontend/e2e/visual/chat-surface.spec.ts` — visual regression spec.
- `justfile` — `uat`, `uat-smoke`, `uat-visual`, `uat-baselines`.
</files_to_read>
