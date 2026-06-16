---
phase: 06-postgres-redis-docker-compose
plan: 05b
type: execute
wave: 5
depends_on:
  - 06-04
  - 06-05a
files_modified:
  - frontend/src/types/chat.ts
  - frontend/src/hooks/useChat.ts
  - frontend/src/hooks/useConversations.ts
  - frontend/src/lib/chatConversationStore.ts
  - frontend/src/lib/providerSettings.ts
  - frontend/src/components/ChatInterface.tsx
  - frontend/src/components/Sidebar.tsx
  - frontend/src/components/ProviderSelector.tsx
  - frontend/src/components/ToolExecutionCard.tsx
  - .planning/phases/06-postgres-redis-docker-compose/06-05b-SUMMARY.md
autonomous: true
requirements:
  - REQ-p5-conversation-rename
tags:
  - rename
  - frontend-coordination
  - phase-5-carryforward
  - frontend-only

must_haves:
  truths:
    - "Frontend production code references zero `session_id` / `sessionId` / `/api/chat/sessions` / `/api/chat/session` tokens outside `auth/SessionExpired*` (JWT-lifetime usage explicitly preserved per D-03)"
    - "Renamed files exist: `frontend/src/lib/chatConversationStore.ts` (replaces `chatSessionStore.ts`) and `frontend/src/hooks/useConversations.ts` (replaces `useSessions.ts`); old paths no longer exist"
    - "TypeScript SSE event types in `frontend/src/types/chat.ts` mirror the 06-05a backend wire format — `conversation_id: string` declared LAST per event interface"
    - "`frontend/src/lib/providerSettings.ts` decodes the discriminated `ProviderInfoResponse` shape: switch on `entry.type` to extract `base_url` (local) vs `api_key_configured` (cloud); no field treats `api_key` as present on the wire"
    - "`frontend/src/components/auth/SessionExpiredFlash.tsx` is unchanged (D-03 reserved-word boundary preserved)"
    - "`npm run build` succeeds and `npm test -- --run` passes — Vitest tests under `frontend/src/components/__tests__/`, `frontend/src/hooks/__tests__/`, and `frontend/src/lib/__tests__/` are updated to the renamed identifiers"
  artifacts:
    - path: "frontend/src/types/chat.ts"
      provides: "TypeScript types renamed to ConversationId / conversation_id; SSE event types match 06-05a backend wire format"
    - path: "frontend/src/lib/chatConversationStore.ts"
      provides: "Renamed conversation snapshot store (replaces chatSessionStore.ts)"
    - path: "frontend/src/hooks/useConversations.ts"
      provides: "Renamed list hook (replaces useSessions.ts)"
    - path: "frontend/src/lib/providerSettings.ts"
      provides: "Discriminated provider response decoder switching on entry.type"
  key_links:
    - from: "frontend/src/hooks/useChat.ts"
      to: "/api/chat/conversation"
      via: "apiFetch('/api/chat/conversation', ...)"
      pattern: "/api/chat/conversation"
    - from: "frontend/src/types/chat.ts::SSEEvent subtypes"
      to: "backend/app/chat/models.py::StreamEvent subtypes (Plan 06-05a)"
      via: "wire field name `conversation_id` (LAST in JSON)"
      pattern: "conversation_id: string"
    - from: "frontend/src/lib/providerSettings.ts"
      to: "backend/app/providers/models.py::ProviderInfoResponse (Plan 06-05a)"
      via: "switch on entry.type — LocalProviderInfo vs CloudProviderInfo"
      pattern: "entry\\.type === ['\"]local['\"]"
---

<objective>
Frontend slice of the Phase 5 carry-forward refactor: rename `session` → `conversation` across `frontend/src/` (D-03), update TypeScript types to mirror the 06-05a backend wire format, rename `chatSessionStore.ts` → `chatConversationStore.ts` and `useSessions.ts` → `useConversations.ts`, and update `providerSettings.ts` to decode the discriminated `ProviderInfoResponse` shape (LocalProviderInfo vs CloudProviderInfo) shipped by 06-05a.

Purpose: 06-05a publishes the new backend wire format; this plan ships the frontend that consumes it. Both plans land in a single atomic PR per RESEARCH OQ-5 — the wave-5 dependency `[06-04, 06-05a]` enforces sequencing within execute-phase so backend types are present in the working tree before frontend rebuilds against them. The wire-format ownership stays in 06-05a (REQ-p5-session-create-request-split, REQ-p5-provider-info-split); REQ-p5-conversation-rename is jointly covered (the rename is end-to-end but the wire-format-defining identifiers — Pydantic class field declarations, SSE event field-order — live on the backend).
Output: rename-complete frontend, discriminated provider decoder, all Vitest tests green, `npm run build` green, `auth/SessionExpiredFlash.tsx` unchanged.
</objective>

<execution_context>
@/Users/axel/code/trip_planner/.claude/get-shit-done/workflows/execute-plan.md
@/Users/axel/code/trip_planner/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/06-postgres-redis-docker-compose/06-CONTEXT.md
@.planning/phases/06-postgres-redis-docker-compose/06-RESEARCH.md
@.planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md
@.planning/phases/06-postgres-redis-docker-compose/06-VALIDATION.md
@.planning/phases/06-postgres-redis-docker-compose/06-05a-SUMMARY.md
@CLAUDE.md
@frontend/src/types/chat.ts
@frontend/src/hooks/useChat.ts
@frontend/src/hooks/useSessions.ts
@frontend/src/lib/chatSessionStore.ts
@frontend/src/components/ChatInterface.tsx
@frontend/src/lib/providerSettings.ts

<interfaces>
<!-- Wire format the frontend mirrors (published by Plan 06-05a): -->
- SSE event TS interfaces — every `session_id: string` field becomes `conversation_id: string` and stays declared LAST in the interface body to match Pydantic's per-subclass JSON serialisation order.
- HTTP path strings — `/api/chat/session` → `/api/chat/conversation`; `/api/chat/sessions` → `/api/chat/conversations`; `/api/chat/sessions/{id}` → `/api/chat/conversations/{id}`.
- Request body shape for `POST /api/chat/conversation`:
    ```ts
    interface ConversationCreateRequest {
      target: { provider: string | null; model: string | null };
      credentials?: { base_url: string | null; api_key: string | null };
    }
    ```
- Response shape for `GET /api/providers`:
    ```ts
    type LocalProviderInfo = { type: "local"; available: boolean; models: string[]; base_url: string };
    type CloudProviderInfo = { type: "cloud"; available: boolean; models: string[]; api_key_configured: boolean };
    type ProviderInfoResponse = LocalProviderInfo | CloudProviderInfo;
    ```

<!-- Reserved word — D-03 explicit exclusion (DO NOT RENAME): -->
- `frontend/src/components/auth/SessionExpiredFlash.tsx` and any token containing `Session` that refers to JWT/cookie/login lifetime survives. The rename's grep gates use `grep -v 'auth/SessionExpired' | grep -v 'JWT\|jwt\|expir'` to exclude these from the zero-match audit.

<!-- File renames (use git mv to preserve history): -->
- `frontend/src/lib/chatSessionStore.ts` → `frontend/src/lib/chatConversationStore.ts`
- `frontend/src/hooks/useSessions.ts` → `frontend/src/hooks/useConversations.ts`

<!-- Identifier renames (camelCase TS state — distinct from snake_case wire fields): -->
- `sessionId` → `conversationId`
- `setSessionId` → `setConversationId`
- `activeSessionIdRef` → `activeConversationIdRef`
- `ownedSessionIdRef` → `ownedConversationIdRef`
- `getSessionSnapshot` → `getConversationSnapshot`
- `setSession` (in chatSessionStore) → `setConversation`
- `clearSession` → `clearConversation`
- `useSessions` hook → `useConversations` hook
</interfaces>
</context>

### Cross-plan coordination

- **Depends on 06-04 + 06-05a:** This plan rebuilds the frontend against types that 06-05a publishes on the backend. Plan 06-04 is also a hard prerequisite because the route handlers consuming `ConversationCreateRequest` only exist after 06-04 wires the placeholder deps + 06-05a renames the handlers.
- **Atomic PR semantics:** 06-05a + 06-05b land in a single squash-merge. `master` between the 06-05a and 06-05b commits is broken-by-design (frontend cannot compile against backend types while the rename is half-applied). Execute-phase enforces this by running 06-05b immediately after 06-05a in the same wave.

<tasks>

<task type="auto">
  <name>Task 1: Frontend rename — `session_id` / `sessionId` / `/api/chat/session*` → conversation across types, hooks, components, providerSettings</name>
  <files>frontend/src/types/chat.ts, frontend/src/hooks/useChat.ts, frontend/src/hooks/useConversations.ts, frontend/src/lib/chatConversationStore.ts, frontend/src/lib/providerSettings.ts, frontend/src/components/ChatInterface.tsx, frontend/src/components/Sidebar.tsx, frontend/src/components/ProviderSelector.tsx, frontend/src/components/ToolExecutionCard.tsx</files>
  <read_first>
    - frontend/src/types/chat.ts (full file — every SSE event subtype with `session_id: string`)
    - frontend/src/hooks/useChat.ts (full file — `apiFetch('/api/chat/session', ...)`, `setSessionId`, `sessionId` state, `result.data.session_id`)
    - frontend/src/hooks/useSessions.ts (full file — `apiFetch('/api/chat/sessions')`, `s.session_id`)
    - frontend/src/lib/chatSessionStore.ts (full file — `chatSessionStore`, `Map<sessionId,...>`, `getSnapshot`, `setSession`, `clearSession`)
    - frontend/src/components/ChatInterface.tsx (sessionId state binding to URL/SSE)
    - frontend/src/components/Sidebar.tsx, ProviderSelector.tsx, ToolExecutionCard.tsx (any session-token references)
    - frontend/src/components/auth/SessionExpiredFlash.tsx (reserved D-03 — DO NOT rename; this is JWT-session-expiry, not chat-conversation)
    - frontend/src/lib/auth.ts (any `/api/chat/session*` references — there should be none; auth uses `/api/auth/*`)
    - frontend/src/lib/providerSettings.ts (provider response decoder — must adapt to discriminated `ProviderInfoResponse` shape from 06-05a)
    - .planning/phases/06-postgres-redis-docker-compose/06-CONTEXT.md (D-03 reserved-word boundary — JWT/auth session preserved)
    - .planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md (frontend rename inventory — ~30+ files; SessionExpiredFlash exempt)
    - .planning/phases/06-postgres-redis-docker-compose/06-05a-SUMMARY.md (for the published wire-format contract this plan consumes)
    - CLAUDE.md `/react-stack` skill routing — React 19 + TypeScript + Vitest patterns; immutable state, hook conventions
    - CLAUDE.md `/chakra-ui` skill — if any UI component touched here uses Chakra v3 slot recipes
  </read_first>
  <action>
    Apply the mechanical rename across `frontend/src/`, EXCLUDING `frontend/src/components/auth/SessionExpiredFlash.tsx` and any token containing `Session` that refers to JWT/cookie/login lifetime (per D-03):
      - identifiers: `session_id` → `conversation_id` (snake_case wire field); `sessionId` → `conversationId` (camelCase TS state); `setSessionId` → `setConversationId`; `activeSessionIdRef` → `activeConversationIdRef`; `ownedSessionIdRef` → `ownedConversationIdRef`; `getSessionSnapshot` → `getConversationSnapshot`; `setSession` → `setConversation` (in `chatSessionStore`); `clearSession` → `clearConversation`.
      - file rename: `frontend/src/lib/chatSessionStore.ts` → `frontend/src/lib/chatConversationStore.ts` (use `git mv` so history follows). Update every import site accordingly.
      - file rename: `frontend/src/hooks/useSessions.ts` → `frontend/src/hooks/useConversations.ts`; export hook becomes `useConversations`.
      - HTTP path string literals: `'/api/chat/session'` → `'/api/chat/conversation'`; `'/api/chat/sessions'` → `'/api/chat/conversations'`; `/api/chat/session/{id}` → `/api/chat/conversation/{id}`.
      - TypeScript types in `types/chat.ts`: every SSE event interface field `session_id: string` → `conversation_id: string`. Keep field declaration order consistent with the backend Pydantic emit order (the `conversation_id` field stays last in the wire JSON — mirror this in the TS interface body for clarity).
      - Comments: `session_id` in code comments rewrites to `conversation_id` *unless* the comment is explicitly about JWT/auth-session expiry behaviour (rare — the Sidebar list-fetcher mentions "session" in a couple of places that mean chat-conversation; rename those).
    Update `frontend/src/lib/providerSettings.ts` (and any consumer) to match the new discriminated `ProviderInfoResponse`:
      - introduce TypeScript types `LocalProviderInfo` (`{type:"local"; available:boolean; models:string[]; base_url:string}`) and `CloudProviderInfo` (`{type:"cloud"; available:boolean; models:string[]; api_key_configured:boolean}`). Export them from `providerSettings.ts` so consumers can narrow.
      - the response decoder switches on `entry.type` to extract `base_url` (local) vs `api_key_configured` (cloud); the existing UI logic that read `entry.base_url` for cloud providers (defaulted to `null`) must change to fall back to `entry.api_key_configured` for the cloud branch.
      - keep the same UI surface — just adapt the data shape. If the existing UI passes a single `ProviderInfo` shape downstream, update the consumer interface to accept the discriminated union and switch on `type`.
    Hygiene gate: `rg --no-filename 'session_id|sessionId|/api/chat/sessions|/api/chat/session\b' frontend/src | grep -v 'auth/SessionExpired\|JWT\|jwt\|expir' | grep -v '^\s*//' | wc -l` returns 0.
    Update Vitest tests under `frontend/src/components/__tests__/` and `frontend/src/hooks/__tests__/` (and `frontend/src/lib/__tests__/`) to match the renamed identifiers + types. Many of these tests will compile-fail after the rename — fix them in this task; do not skip.
    Run `npm run build` (frontend) and `npm run lint` to confirm zero residual references and a clean compile.
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; npm run build &amp;&amp; npm test -- --run &amp;&amp; rg --no-filename 'session_id|sessionId|/api/chat/sessions|/api/chat/session\b' src | grep -v 'auth/SessionExpired\|JWT\|jwt\|expir' | grep -v '^\s*//' | wc -l | tr -d ' ' | grep -qx 0</automated>
  </verify>
  <acceptance_criteria>
    - `rg --no-filename 'session_id|sessionId' frontend/src | grep -v 'auth/SessionExpired' | grep -v 'JWT\|jwt\|expir' | grep -v '^\s*//'` returns zero non-comment matches.
    - `rg '/api/chat/sessions|/api/chat/session\b' frontend/src | grep -v '^\s*//'` returns zero matches.
    - The renamed files (`chatConversationStore.ts`, `useConversations.ts`) exist; old filenames no longer exist (`git ls-files` does not list them).
    - `frontend/src/components/auth/SessionExpiredFlash.tsx` is unchanged (verified by `git diff --stat phase/06-postgres-redis-compose -- frontend/src/components/auth/SessionExpiredFlash.tsx` returning empty).
    - `npm run build` succeeds; `npm test -- --run` passes (all updated Vitest tests green).
    - `frontend/src/lib/providerSettings.ts` switches on `entry.type` and resolves `LocalProviderInfo` vs `CloudProviderInfo` correctly; UI continues to render the settings page without runtime errors (smoke-tested via existing Vitest suite).
  </acceptance_criteria>
  <done>Frontend production code is rename-complete; the discriminated provider response is consumed correctly; all Vitest tests pass; legacy SessionExpiredFlash remains intact per D-03.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → `POST /api/chat/conversation` | Request body composed in TS; the SSRF + length validators live on the backend (06-05a `ProviderCredentials`) — frontend MUST NOT mirror those validators (avoid drift; one source of truth) |
| Backend SSE stream → React EventSource | Wire field name `conversation_id` crosses; TS interface MUST mirror backend declaration order (LAST in JSON) for any code that does ordered key iteration |
| Auth-side session lifetime → JWT cookie | D-03 reserved-word boundary — `SessionExpiredFlash.tsx` and JWT-session tokens preserved unchanged |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-05b-01 | Tampering | Frontend `providerSettings.ts` decoder accepting unknown discriminator value | mitigate | Decoder switches on `entry.type`; an unknown discriminator falls through a default branch that logs and skips the entry rather than rendering a corrupt UI. Test in Vitest suite covers the unknown-type path. |
| T-06-05b-02 | Information Disclosure | Frontend caching `api_key` from settings UI | mitigate | The discriminated response contract from 06-05a never carries `api_key` over the wire. Frontend types reflect that — `CloudProviderInfo.api_key_configured: boolean` is the only credential signal. The settings UI continues to send user-typed `api_key` only on `POST /api/chat/conversation` (in-memory only; D-09 lock from Phase 5). |
| T-06-05b-03 | Tampering | Rename window leaving `master` broken between 06-05a and 06-05b commits | mitigate | Atomic PR squash-merge: 06-05a + 06-05b land as a single push (RESEARCH OQ-5). Wave-5 dependency `[06-04, 06-05a]` enforces sequencing in execute-phase. CI runs against the squashed commit, not the intermediate state. |
| T-06-05b-04 | Repudiation | Reserved-word boundary regression — accidental rename of `SessionExpiredFlash.tsx` | mitigate | Acceptance criterion explicitly asserts `git diff` is empty for `SessionExpiredFlash.tsx`. The grep gates exclude `auth/SessionExpired*` from the zero-match audit (D-03). |
| T-06-05b-SC | Tampering | npm/pip/cargo installs | accept | No new packages installed in this plan; `package.json` unchanged. Audit table from Plan 01 covers the existing pinned set. |
</threat_model>

<verification>
- `cd frontend && npm run build && npm test -- --run` passes.
- `rg --no-filename 'session_id|sessionId' frontend/src | grep -v 'auth/SessionExpired' | grep -v 'JWT\|jwt\|expir' | grep -v '^\s*//'` returns zero matches.
- `rg '/api/chat/sessions|/api/chat/session\b' frontend/src | grep -v '^\s*//'` returns zero matches.
- `git ls-files frontend/src/lib/chatSessionStore.ts frontend/src/hooks/useSessions.ts` returns empty (old paths gone).
- `git ls-files frontend/src/lib/chatConversationStore.ts frontend/src/hooks/useConversations.ts` returns both paths (new paths committed).
- `git diff --stat -- frontend/src/components/auth/SessionExpiredFlash.tsx` is empty (D-03 reserved boundary preserved).
</verification>

<success_criteria>
- `session` → `conversation` rename complete on frontend production code; auth-side `session` (JWT lifetime) preserved per D-03.
- File renames committed via `git mv`: `chatSessionStore.ts` → `chatConversationStore.ts`, `useSessions.ts` → `useConversations.ts`.
- TypeScript SSE event types mirror the 06-05a backend wire format with `conversation_id: string` declared LAST.
- `providerSettings.ts` decoder switches on `entry.type` to handle `LocalProviderInfo` vs `CloudProviderInfo`; UI continues to render without runtime errors.
- `npm run build` succeeds; all Vitest tests pass after identifier and type updates.
- `auth/SessionExpiredFlash.tsx` is bit-for-bit unchanged.
</success_criteria>

<output>
Create `.planning/phases/06-postgres-redis-docker-compose/06-05b-SUMMARY.md` when done.
</output>
</content>
</invoke>