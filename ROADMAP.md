# Trip Planner - Development Roadmap

**Last Updated**: 2025-11-14

## Current Status
- **Active Phase**: Phase 3 ✅ COMPLETE
- **Next Phase**: Phase 4 - LLM Provider Flexibility & UI Polish
- **Current Focus**: Detailed priorities tracked separately
- **Blockers**: None

---

## Phase Overview

### ✅ Phase 1: Foundation & FastAPI Setup
**Goal**: Project structure with proper tooling, basic FastAPI server

**Completed**: 2025-11-06 → 2025-11-08

<details>
<summary>Key Deliverables</summary>

- Python 3.13 + uv dependency management
- FastAPI with health check endpoint
- ruff, mypy, pytest configured
- Frontend: Vite + React + TypeScript + Chakra UI v3
- justfile for common commands
- Monorepo structure

</details>

---

### ✅ Phase 2: LangChain Integration & Chat Agent
**Goal**: Working chat agent with LangChain and Ollama

**Completed**: 2025-11-08 → 2025-11-10

<details>
<summary>Key Deliverables</summary>

- LangChain 1.0 with `RunnableWithMessageHistory`
- Ollama integration (deepseek-r1:8b → qwen3:8b)
- Session-based conversation memory
- Streaming chat via Server-Sent Events
- React chat UI with markdown rendering
- 109 unit/integration tests passing

</details>

---

### ✅ Phase 3: Mock Flight Search Tool
**Goal**: Agent can call flight search tool and incorporate results

**Completed**: 2025-11-10 → 2025-11-14

<details>
<summary>Key Deliverables</summary>

- Pydantic models: `FlightQuery`, `Flight`
- Abstract client pattern: `FlightAPIClient` ABC
- `MockFlightAPIClient` with realistic data
- `FlightService` with business logic (sorting, filtering)
- LangChain tool with `@tool` decorator + `bind_tools()`
- Streaming agent responses with tool calls
- Frontend: `ToolExecutionCard` + `ThinkingCard` components
- SSE event structure: flat tool metadata (tool_name, tool_args, tool_result)
- Thinking/reasoning display with `reasoning=True` in init_chat_model
- Session management with multi-tab support
- 56/76 tests passing (20 E2E tests skipped by default)
- Model: qwen3:4b with reasoning mode

</details>

---

### � Phase 4: LLM Provider Flexibility & UI Polish
**Goal**: Support multiple LLM providers + enhanced user experience

**Status**: READY TO START (Phase 3 complete)

**Estimated**: 12-18 hours

**Key Deliverables**:

<details>
<summary>High Priority Tasks</summary>

1. **LLM Provider UI & Configuration** (4-6h)
   - Frontend dropdown to select provider (Ollama/OpenAI/Anthropic)
   - Config API endpoint to list available models per provider
   - Session-level provider selection (stored in metadata)
   - Support for API keys in config

2. **Structured Tool Output** (2-3h)
   - Return JSON objects from tools instead of strings
   - Enhanced ToolResultCard with table/list rendering
   - Pretty-print structured data

3. **Error Handling & Feedback** (2-3h)
   - Better error messages in UI
   - Loading states for tool execution
   - Retry mechanism for failed calls
   - Toast notifications

</details>

<details>
<summary>Medium Priority Tasks</summary>

4. **Frontend State Management** (3-4h)
   - Replace useState with useReducer
   - Centralized message event handling
   - Better TypeScript types

5. **Testing & Polish** (2-3h)
   - Tests for SSE event handling
   - E2E tests for tool visibility
   - Frontend component tests

</details>

**What Was Dropped from Original "Pre-Phase 4"**:
- ❌ Session management refactor (already working well)
- ❌ Dependency injection fixes (no issues found)
- ❌ Global store removal (never existed)
- ✅ Kept: LLM provider abstraction, structured tool output, state management

---

### 📋 Phase 5: Real API Integration
**Goal**: Replace mock with real Amadeus API

**Status**: PLANNED

<details>
<summary>Key Tasks</summary>

- Amadeus API credentials setup
- Async flight search with real API
- Rate limiting + caching
- Retry logic for transient failures
- Comprehensive error handling

</details>

---

### 📋 Phase 6: Production Readiness
**Goal**: Make MVP production-ready

**Status**: PLANNED

<details>
<summary>Key Tasks</summary>

- Comprehensive logging
- API documentation (OpenAPI/Swagger)
- Docker setup for deployment
- Performance optimization
- Security review
- Conversation cost tracking

</details>

---

## Future Enhancements (Post-MVP)
- Database & persistence (PostgreSQL)
- User authentication (JWT)
- GraphQL migration
- Additional tools (hotels, restaurants, weather)
- DSPy integration
- Multi-city trip support
