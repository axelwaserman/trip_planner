# Architecture

**Analysis Date:** 2026-04-27

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite)                      │
│         `frontend/src/components/ChatInterface.tsx`           │
│   Chakra UI v3  |  SSE streaming  |  Provider selection      │
└────────────────────────────┬────────────────────────────────┘
                             │  HTTP (proxied via Vite /api)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (uvicorn)                   │
│            `backend/app/api/main.py`                          │
├──────────────────┬──────────────────┬───────────────────────┤
│  Routes Layer    │   Chat Service   │    Tools Layer         │
│ `app/api/routes/ │  `app/chat.py`   │  `app/tools/`         │
│  routes.py`      │                  │  flight_search.py     │
│  `auth.py`       │                  │  flight_client.py     │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────┐ ┌──────────────────┐ ┌────────────────────┐
│  Pydantic       │ │  LangChain Core  │ │  Mock Flight API   │
│  Models         │ │  + Ollama/OpenAI │ │  Client (ABC)      │
│  `app/models.py`│ │  + Anthropic     │ │  `app/tools/       │
│                 │ │                  │ │   flight_client.py` │
└─────────────────┘ └──────────────────┘ └────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| App entrypoint | FastAPI lifespan, CORS, DI overrides, router inclusion | `backend/app/api/main.py` |
| Routes | HTTP endpoints: chat SSE, session CRUD, health, providers | `backend/app/api/routes/routes.py` |
| Auth Routes | Placeholder OAuth2 password flow (fake DB) | `backend/app/api/routes/auth.py` |
| ChatService | LLM conversation management, tool orchestration, session history, streaming | `backend/app/chat.py` |
| Config | Pydantic settings, LLM provider/model config, env loading | `backend/app/config.py` |
| Models | Pydantic domain models (Flight, FlightQuery, StreamEvent, ChatRequest) | `backend/app/models.py` |
| Exceptions | Typed exception hierarchy with retryable flag | `backend/app/exceptions.py` |
| Flight Search Tool | LangChain `@tool` for LLM-invoked flight search | `backend/app/tools/flight_search.py` |
| Flight Client | ABC + MockFlightAPIClient for flight data | `backend/app/tools/flight_client.py` |
| Retry Decorator | Exponential backoff for async functions | `backend/app/tools/retry.py` |
| ChatInterface | Main React UI: message list, SSE reader, input form | `frontend/src/components/ChatInterface.tsx` |
| ProviderSelector | Provider/model dropdown, localStorage persistence | `frontend/src/components/ProviderSelector.tsx` |
| ToolExecutionCard | Combined tool call + result display | `frontend/src/components/ToolExecutionCard.tsx` |
| ThinkingCard | LLM reasoning token display with expand/collapse | `frontend/src/components/ThinkingCard.tsx` |

## Pattern Overview

**Overall:** Monorepo with separate backend (Python/FastAPI) and frontend (React/Vite) communicating via REST + SSE.

**Key Characteristics:**
- Backend uses a service-layer pattern: routes delegate to `ChatService` which orchestrates LLM + tools
- LangChain `bind_tools()` pattern for LLM tool calling (no agent framework)
- In-memory session storage with `InMemoryChatMessageHistory` (no database)
- Server-Sent Events (SSE) for real-time streaming to frontend
- Abstract base class pattern for flight API client (swap mock for real API)
- Dependency injection via FastAPI `Depends()` with `app.state` override

## Layers

**API Layer (Routes):**
- Purpose: Accept HTTP requests, validate input, delegate to services, format responses
- Location: `backend/app/api/routes/`
- Contains: FastAPI route handlers, dependency definitions, SSE event generators
- Depends on: `ChatService`, `Settings`, Pydantic request/response models
- Used by: Frontend via HTTP

**Service Layer:**
- Purpose: Business logic, LLM orchestration, session management
- Location: `backend/app/chat.py`
- Contains: `ChatService` class with `chat_stream()`, session CRUD, history management
- Depends on: LangChain `BaseChatModel`, `FlightAPIClient`, `InMemoryChatMessageHistory`
- Used by: Routes layer

**Tools Layer:**
- Purpose: LangChain tools callable by the LLM during conversations
- Location: `backend/app/tools/`
- Contains: `search_flights` tool function, `FlightAPIClient` ABC, `MockFlightAPIClient`, retry decorator
- Depends on: Pydantic models, exception hierarchy
- Used by: `ChatService` (bound to LLM via `bind_tools()`)

**Domain Layer:**
- Purpose: Data models, validation, type definitions
- Location: `backend/app/models.py`, `backend/app/exceptions.py`
- Contains: Pydantic models (`Flight`, `FlightQuery`, `StreamEvent`, `ChatRequest`, etc.), exception classes
- Depends on: Pydantic, standard library
- Used by: All other layers

**Configuration:**
- Purpose: Application settings, environment loading, provider discovery
- Location: `backend/app/config.py`
- Contains: `Settings` class with `get_available_providers()`, module-level `settings` singleton
- Depends on: `pydantic-settings`
- Used by: Routes, `main.py` lifespan

**Frontend:**
- Purpose: Chat UI, SSE consumption, LLM provider selection
- Location: `frontend/src/`
- Contains: React components with Chakra UI v3, SSE reader, state management (useState)
- Depends on: Chakra UI, react-markdown, backend API
- Used by: End users via browser

## Data Flow

### Primary Chat Flow (User Message to Streamed Response)

1. User types message in `ChatInterface`, form submit fires `sendMessage()` (`frontend/src/components/ChatInterface.tsx:98`)
2. Frontend POSTs to `/api/chat` with `{ message, session_id }` (proxied by Vite to `localhost:8000`)
3. Route handler `chat()` gets `ChatService` via DI, calls `chat_service.chat_stream()` (`backend/app/api/routes/routes.py:26`)
4. `ChatService.chat_stream()` loads session history, builds message list, streams LLM via `self.llm.astream(messages)` (`backend/app/chat.py:97`)
5. For each LLM chunk, yields `StreamEvent` (types: `thinking`, `content`, `tool_call`, `tool_result`) (`backend/app/chat.py:131-216`)
6. If LLM invokes `search_flights` tool, executes it inline and yields tool events, then re-streams LLM with tool results (`backend/app/chat.py:156-218`)
7. Route formats each `StreamEvent` as `data: {json}\n\n` SSE format (`backend/app/api/routes/routes.py:54`)
8. Frontend `ReadableStream` reader parses SSE lines, updates React state immutably (`frontend/src/components/ChatInterface.tsx:137-261`)
9. After stream ends, history is persisted in `InMemoryChatMessageHistory` (`backend/app/chat.py:221-228`)

### Session Creation Flow

1. Frontend calls `POST /api/chat/session` with optional `{ provider, model }` (`frontend/src/components/ChatInterface.tsx:56`)
2. Route validates provider/model against `settings.get_available_providers()` (`backend/app/api/routes/routes.py:85`)
3. `ChatService.create_session()` generates UUID, stores empty history + metadata (`backend/app/chat.py:36`)
4. Response includes `session_id`, `provider`, `model` -- frontend stores in state and localStorage

### Provider Selection Flow

1. `ProviderSelector` fetches `GET /api/providers` on mount (`frontend/src/components/ProviderSelector.tsx:32`)
2. On change, saves to `localStorage` and calls `onProviderChange` callback (`frontend/src/components/ProviderSelector.tsx:61`)
3. `ChatInterface` clears messages and creates new session with new provider/model (`frontend/src/components/ChatInterface.tsx:93`)

**State Management:**
- Backend: In-memory dicts on `ChatService` (`_histories`, `_metadata`, `_last_activity`). No database.
- Frontend: React `useState` hooks for messages, session ID, loading state, provider/model. Provider config persisted in `localStorage`.

## Key Abstractions

**FlightAPIClient (ABC):**
- Purpose: Abstract interface for flight search operations (search, details, availability, health)
- Examples: `backend/app/tools/flight_client.py` -- `FlightAPIClient` (ABC), `MockFlightAPIClient` (concrete)
- Pattern: Strategy pattern -- swap implementations without changing consumers

**ChatService:**
- Purpose: Encapsulates all LLM interaction, tool binding, session management, and streaming
- Examples: `backend/app/chat.py`
- Pattern: Service class with constructor-injected dependencies (LLM, flight client)

**StreamEvent:**
- Purpose: Typed SSE event envelope for all stream data (content, tool calls, thinking)
- Examples: `backend/app/models.py:160`
- Pattern: Discriminated union via `type` field (`content | tool_call | tool_result | thinking`)

**Settings:**
- Purpose: Centralized configuration with env var loading and provider discovery
- Examples: `backend/app/config.py`
- Pattern: Pydantic BaseSettings singleton

## Entry Points

**Backend Server:**
- Location: `backend/app/api/main.py` (the `app` object)
- Triggers: `uv run uvicorn app.api.main:app --reload` (see `justfile`)
- Responsibilities: Creates FastAPI app, configures CORS, lifespan initializes `ChatService`, `MockFlightAPIClient`, and LLM; registers routes

**Frontend Dev Server:**
- Location: `frontend/src/main.tsx`
- Triggers: `npm run dev` (Vite)
- Responsibilities: Mounts React app with `ChakraProvider` into DOM root

**Test Runner:**
- Location: `backend/tests/` (pytest discovers from `tests/` per `pyproject.toml`)
- Triggers: `uv run pytest` or `just test`
- Responsibilities: Unit, integration, E2E tests with markers (`unit`, `integration`, `e2e`, `slow`)

## Architectural Constraints

- **Threading:** Backend uses Python asyncio event loop (single-threaded). All I/O must use `async/await`. CPU-bound work blocks the loop.
- **Global state:** `ChatService` instance stored on `app.state.chat_service` (module-level in lifespan). `settings` is a module-level singleton in `backend/app/config.py:80`. Session data lives in `ChatService._histories` dict (in-memory, lost on restart).
- **Circular imports:** None detected. Tool module uses `TYPE_CHECKING` guard for `FlightAPIClient` import in `backend/app/tools/flight_search.py:6`.
- **No database:** All session/conversation data is in-memory. No persistence layer, no ORM, no migrations.
- **Tool injection hack:** `search_flights._flight_client` is set as an attribute on the tool function object (`backend/app/chat.py:31` and `backend/app/api/main.py:45`). Not a standard DI pattern.
- **Single tool:** Only `search_flights` is bound to the LLM. Adding new tools requires modifying `ChatService.__init__()` and the tool dispatch in `chat_stream()`.

## Anti-Patterns

### Monkey-Patched Tool Dependency

**What happens:** The `search_flights` LangChain tool gets its `FlightAPIClient` injected via `search_flights._flight_client = flight_client` (attribute set on the function object).
**Why it's wrong:** Breaks type safety, invisible dependency, makes testing harder, and the attribute is not declared on the function type.
**Do this instead:** Use LangChain's `tool` configuration or a closure pattern to inject the client. See `backend/app/tools/flight_search.py:78` and `backend/app/chat.py:31`.

### Fake Auth Implementation

**What happens:** `backend/app/api/routes/auth.py` uses hardcoded `fake_users_db` dict, `fake_hash_password()`, and returns username as access token.
**Why it's wrong:** Zero security. The token is literally the username string. No real hashing, no JWT, no expiry.
**Do this instead:** Implement JWT-based auth per the FastAPI skill pattern (`pyjwt` + `bcrypt` are already in dependencies).

### Direct Private Attribute Access

**What happens:** Routes access `chat_service._metadata[session_id]` and `chat_service._histories` directly (`backend/app/api/routes/routes.py:130,164`).
**Why it's wrong:** Breaks encapsulation. Routes should not know about `ChatService` internal data structures.
**Do this instead:** Add public methods to `ChatService` like `get_session_metadata()` and `delete_session()`.

## Error Handling

**Strategy:** Multi-layer error handling with typed exceptions.

**Patterns:**
- Custom exception hierarchy in `backend/app/exceptions.py` with `retryable` flag for retry decisions
- `search_flights` tool catches all exceptions and returns error strings (never raises to LLM) (`backend/app/tools/flight_search.py:175-178`)
- SSE event generator catches `ValueError` (session not found) and generic `Exception`, converts to error `StreamEvent` (`backend/app/api/routes/routes.py:57-72`)
- Retry decorator with exponential backoff in `backend/app/tools/retry.py` (available but not actively used in current code)
- Frontend catches fetch errors and displays fallback error messages (`frontend/src/components/ChatInterface.tsx:266-275`)

## Cross-Cutting Concerns

**Logging:** Uses Python `logging` module in retry decorator (`backend/app/tools/retry.py:14`). `print()` used in lifespan shutdown (`backend/app/api/main.py:60`). Frontend uses `console.log/console.error` liberally.

**Validation:** Pydantic `Field()` constraints and `@field_validator` on all domain models. Input validation in `search_flights` tool before creating `FlightQuery`. FastAPI auto-validates request bodies.

**Authentication:** Placeholder only. Fake OAuth2 password flow in `backend/app/api/routes/auth.py`. Chat endpoints have no auth protection.

**CORS:** Configured for `http://localhost:5173` (Vite dev server) in `backend/app/api/main.py:71-77`.

---

*Architecture analysis: 2026-04-27*
