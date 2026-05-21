---
name: react-stack
description: |
  Build and extend the Trip Planner React frontend using Vite 5, React 19, TypeScript strict mode, Chakra UI v3, and Vitest. Covers project hook conventions, wire-contract type definitions, Chakra token patterns, and Vitest setup.

  ALWAYS USE when detecting: Vite, React, TypeScript, .tsx, .ts (frontend), useChat, useSSEStream, parseSSE, ChatStreamEvent, Message, MessageType, Chakra theme tokens, vitest, @testing-library/react, or any edit inside frontend/src/.

  Use when: adding or editing React components, writing or editing hooks, working with SSE streaming logic, writing Vitest tests, updating Chakra theme tokens, touching frontend type definitions, or debugging frontend rendering issues.
user-invocable: true
---

# React Stack Skill

Project-specific patterns for the Trip Planner frontend: Vite 5 + React 19 + TypeScript strict mode + Chakra UI v3 + Vitest.

**Versions in use (as of Phase 4.9):**

- Vite: 5.x
- React: 19.x
- TypeScript: 5.x (strict mode)
- Chakra UI: v3 (`@chakra-ui/react`)
- Vitest: latest (jsdom environment)
- React Testing Library: `@testing-library/react`
- Coverage: `@vitest/coverage-v8`

---

## Stack Overview

| Layer | Package | Notes |
|-------|---------|-------|
| Build | Vite 5 | `frontend/vite.config.ts`; proxies `/api/*` to `localhost:8000` |
| UI framework | React 19 | JSX transform via `@vitejs/plugin-react` |
| Language | TypeScript strict | `tsconfig.json` strict mode; no `any` in app code |
| Component lib | `@chakra-ui/react` v3 | Custom theme at `src/theme/index.ts` |
| Test runner | Vitest | jsdom environment; setup in `src/test-setup.ts` |
| Test utilities | `@testing-library/react` | React 19 compatible |
| Coverage | `@vitest/coverage-v8` | Reports `text` + `lcov` |

**Vite proxy** (`frontend/vite.config.ts`): all `/api/*` requests are proxied to `http://localhost:8000`. Never use an absolute URL like `http://localhost:8000/api/chat` in frontend code — always use `/api/chat`.

---

## Project Structure

```text
frontend/src/
├── components/         # UI components
│   ├── ChatInterface.tsx       # SSE streaming loop + message state
│   ├── Sidebar.tsx             # Session list, provider selector
│   ├── ProviderCard.tsx        # Provider/model selection card
│   ├── ToolExecutionCard.tsx   # Renders tool_call + tool_result events
│   └── ThinkingCard.tsx        # Renders LLM reasoning tokens
├── hooks/              # Stateful / side-effect hooks
│   ├── useChat.ts              # Primary session lifecycle + SSE streaming hook (~300+ lines)
│   ├── useSSEStream.ts         # Low-level SSE reader (fetch + ReadableStream)
│   ├── useSessions.ts          # Session list management
│   └── useProviderRefresh.ts   # Provider discovery refresh
├── lib/                # Pure utilities
│   ├── parseSSE.ts             # parseSSELine / parseSSE — raw SSE text → ChatStreamEvent
│   ├── auth.ts                 # apiFetch wrapper (attaches JWT Bearer token)
│   ├── chatSessionStore.ts     # External store: getSnapshot, setSession, subscribe
│   ├── providerErrors.ts       # mapProbeError, ProviderErrorView, BackendProbeError
│   ├── providerSettings.ts     # loadProviderSettings, DEFAULT_PROVIDER_SETTINGS, ProviderSettings
│   └── toaster.ts              # Chakra toaster integration
├── types/
│   └── chat.ts                 # Wire-contract types: ChatStreamEvent discriminated union + Message
├── theme/
│   └── index.ts                # Chakra createSystem config (tokens + semantic tokens)
├── App.tsx             # Top-level layout + session init
└── test-setup.ts       # Vitest global setup
```

---

## Hook Conventions

### `useChat` (primary hook)

**Location:** `src/hooks/useChat.ts`

**Purpose:** Owns the full session lifecycle — creates sessions, sends messages, drives the SSE streaming loop, manages message state, and surfaces provider errors.

**Returns (`UseChatReturn`):**

```typescript
interface UseChatReturn {
  messages: Message[]
  isLoading: boolean
  isAwaitingFirstChunk: boolean   // true between submit and first SSE event
  sessionId: string | null
  currentProvider: string
  currentModel: string
  providerError: ProviderErrorView | null
  sendMessage: (text: string) => Promise<void>
  handleProviderChange: (provider: string, model: string) => void
  retryProvider: () => void
  retryLastTool: () => Promise<void>
}
```

**Critical invariant:** `getSessionSnapshot(sessionId).isStreaming` is the re-entrancy guard. Never set streaming state outside the hook. Edits to `useChat.ts` must not break this guard — concurrent calls to `sendMessage` are silently dropped when `isStreaming` is true.

### `readSSEStream` (from `useSSEStream.ts`)

**Purpose:** Low-level SSE reader. Wraps `fetch` + `ReadableStream` to yield raw text lines. Used internally by `useChat`.

**Signature:**

```typescript
async function readSSEStream(
  url: string,
  body: unknown,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal
): Promise<void>
```

### `parseSSELine` / `parseSSE` (from `lib/parseSSE.ts`)

**Purpose:** Parse raw SSE text lines into typed `ChatStreamEvent` objects. Pure functions — no side effects.

```typescript
function parseSSELine(line: string): ChatStreamEvent | null
function parseSSE(chunk: string): ChatStreamEvent[]
```

### `useSessions`

**Purpose:** Manages the session list (load, refresh, delete). Consumed by `Sidebar.tsx`.

### `useProviderRefresh`

**Purpose:** Triggers a `POST /api/providers/refresh` call to rediscover Ollama models. Used when the user manually refreshes the provider list.

---

## Type Definitions (`src/types/chat.ts`)

This file is the **wire contract** between the backend SSE stream and the frontend. Do not add business logic here.

### `ChatStreamEvent` — discriminated union

```typescript
export type ChatStreamEvent =
  | ContentEvent
  | ThinkingEvent
  | ToolCallEvent
  | ToolResultEvent
  | ErrorEvent
```

Each member has a required literal `type` field:

| Type | When emitted |
|------|-------------|
| `ContentEvent` | Text chunks from the LLM |
| `ThinkingEvent` | Reasoning tokens from qwen3 / thinking models |
| `ToolCallEvent` | Before a tool is invoked |
| `ToolResultEvent` | After a tool returns |
| `ErrorEvent` | Session, tool, or stream errors |

**Exhaustive narrowing:**

```typescript
switch (event.type) {
  case 'content':   /* event is ContentEvent */   break
  case 'thinking':  /* event is ThinkingEvent */  break
  case 'tool_call': /* event is ToolCallEvent */  break
  case 'tool_result': /* event is ToolResultEvent */ break
  case 'error':     /* event is ErrorEvent */     break
}
```

### `Message`

```typescript
export interface Message {
  role: MessageType
  content: string
  toolExecution?: ToolExecutionData
}

export type MessageType = 'user' | 'assistant' | 'tool_execution' | 'thinking'
```

### `ErrorEvent`

```typescript
export interface ErrorEvent {
  type: 'error'
  error_code: ErrorCode     // 'session_error' | 'tool_error' | 'stream_error'
  message: string
  retryable: boolean
  tool_name?: string
  raw_detail?: string
  session_id: string
}
```

---

## Chakra UI v3 Patterns

### Custom semantic tokens (`src/theme/index.ts`)

This project uses a custom token set defined with `createSystem(defaultConfig, config)`. Do not use raw palette values — always use these tokens:

| Token | Usage |
|-------|-------|
| `bg.canvas` | Page background (`oklch(98.5% 0.005 95)`) |
| `bg.surface` | Card / panel background (pure white) |
| `fg.primary` | Body text (near-black) |
| `fg.secondary` | Secondary / label text |
| `fg.muted` | Placeholder / disabled text |
| `border.subtle` | Dividers, card borders |
| `border.strong` | Stronger borders, focus rings |
| `accent.solid` | Primary action color (blue) |
| `accent.muted` | Tinted background for accents |
| `danger.solid` | Error / destructive action |
| `danger.muted` | Error background tint |

**Typography tokens:**
- `fonts.display` — `'Fraunces', serif` (headings)
- `fonts.body` — `'Inter', sans-serif` (body text)

### v3 Breaking Changes from v2

| v2 Pattern | v3 Pattern |
|-----------|-----------|
| `colorScheme="blue"` | `colorPalette="blue"` |
| Raw palette: `bg="gray.50"` | Semantic token: `bg="bg.canvas"` |
| `isDisabled` | `disabled` |
| `isLoading` | `loading` |
| `isInvalid` on `Input` | `Field.Root invalid` |

**Never use `colorScheme=` on Chakra v3 components** — it silently does nothing; use `colorPalette=` instead.

### Menu.Item — required unique value

```tsx
// Correct: every Menu.Item needs a unique value prop
<Menu.Item value="settings">Settings</Menu.Item>
<Menu.Item value="logout">Logout</Menu.Item>

// Wrong: missing value prop causes runtime warnings
<Menu.Item>Settings</Menu.Item>
```

### Compound component pattern (v3)

```tsx
import { Menu, Portal } from '@chakra-ui/react'

<Menu.Root onSelect={(details) => handleSelect(details.value)}>
  <Menu.Trigger asChild>
    <Button variant="outline">Actions</Button>
  </Menu.Trigger>
  <Portal>
    <Menu.Positioner>
      <Menu.Content>
        <Menu.Item value="copy">Copy</Menu.Item>
        <Menu.Item value="delete" color="danger.solid">Delete</Menu.Item>
      </Menu.Content>
    </Menu.Positioner>
  </Portal>
</Menu.Root>
```

Always wrap overlays (`Menu`, `Dialog`, `Popover`, `Tooltip`) in `<Portal>` to avoid z-index issues.

---

## Vitest Setup

**Config:** `frontend/vitest.config.ts`

```typescript
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/lib/**', 'src/hooks/**'],
      exclude: ['src/hooks/__tests__/**', 'src/lib/__tests__/**'],
    },
  },
})
```

**Setup file:** `frontend/src/test-setup.ts` — run before each test file; includes global mocks.

**Running tests:**

```bash
# Watch mode (development)
cd frontend && npm test

# Single pass (CI / before commit)
cd frontend && npm test -- --run

# Coverage report
cd frontend && npm run test:coverage
```

**Or via justfile from repo root:**

```bash
# (no justfile shortcut for frontend tests — use npm directly)
cd frontend && npm test -- --run
```

**Test file location convention:** `src/hooks/__tests__/` and `src/lib/__tests__/`.

**Coverage targets:** `src/lib/**` and `src/hooks/**` are included in coverage. Coverage excludes the test directories themselves.

---

## Known Pitfalls

### 1. `colorScheme` does not exist in Chakra v3

```tsx
// Wrong — silently does nothing in v3
<Button colorScheme="blue">Submit</Button>

// Correct
<Button colorPalette="blue">Submit</Button>
```

### 2. Do not hardcode raw palette values

```tsx
// Wrong — bypasses the semantic token system
<Box bg="gray.50" color="blue.600">...</Box>

// Correct — respects light/dark mode overrides and theme updates
<Box bg="bg.canvas" color="accent.solid">...</Box>
```

### 3. `Menu.Item` value prop is required

Every `Menu.Item` must have a unique `value` string prop. Missing or duplicate values produce runtime warnings and broken selection callbacks.

### 4. `useChat` re-entrancy guard

`useChat` uses `getSessionSnapshot(sessionId).isStreaming` as a re-entrancy guard. Any edit to `useChat.ts` must preserve this check. Removing or bypassing it allows concurrent `sendMessage` calls to corrupt message state.

### 5. No absolute URLs in frontend API calls

The Vite dev proxy rewrites `/api/*` to `http://localhost:8000/api/*`. Always use relative paths:

```typescript
// Wrong — breaks in production and behind the proxy
const res = await fetch('http://localhost:8000/api/chat/stream', ...)

// Correct
const res = await fetch('/api/chat/stream', ...)
```

### 6. `apiFetch` is the authenticated fetch wrapper

`src/lib/auth.ts` exports `apiFetch`, which automatically attaches the JWT Bearer token from localStorage. Use it for all authenticated API calls — do not call `fetch` directly for protected endpoints.

```typescript
import { apiFetch } from '../lib/auth'

const res = await apiFetch('/api/chat/session', { method: 'POST', body: ... })
```

---

**Last verified:** 2026-05-21 | **Skill version:** 1.0.0 | **Stack:** Vite 5 + React 19 + TypeScript 5 + Chakra UI v3 + Vitest
