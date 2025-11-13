# Trip Planner - Development Roadmap

**Last Updated**: 2025-11-13

## Current Status
- **Active Phase**: Pre-Phase 4 Refactor (Technical Debt Resolution)
- **Current Task**: Session Management & Multi-Tab Support → See [NOW.md](NOW.md)
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

**Completed**: 2025-11-10 → 2025-11-13

<details>
<summary>Key Deliverables</summary>

- Pydantic models: `FlightQuery`, `Flight`
- Abstract client pattern: `FlightAPIClient` ABC
- `MockFlightAPIClient` with realistic data
- `FlightService` with business logic (sorting, filtering)
- LangChain tool with `@tool` decorator + `bind_tools()`
- Streaming agent responses with tool calls
- Frontend: `ToolExecutionCard` + `ThinkingCard` components
- 122/122 tests passing (13 E2E tests)
- Model: qwen3:8b with reasoning mode

</details>

---

### 🔄 Phase 4 (Pre-Phase): Technical Debt Refactor
**Goal**: Address critical architectural issues before Phase 4 implementation

**Status**: IN PROGRESS (Started 2025-11-13)  
**Estimated**: 17-23 hours over 2-3 days

**Active Tasks** (see [NOW.md](NOW.md) for current focus):
1. 🔄 Session Management & Multi-Tab Support (3-4h)
2. ⏳ LLM Provider Abstraction Layer (4-5h)
3. ⏳ StreamEvent Inheritance (2-3h)
4. ⏳ JSON Tool Output (1-2h)
5. ⏳ Frontend State Management with useReducer (3-4h)
6. ⏳ Structured Logging (2h)
7. ⏳ Pydantic Model Validators (30min)
8. ⏳ Deduplicate Test Logic (1-2h)
9. ⏳ Fix Dependency Injection Pattern (30min)
10. ⏳ XSS Protection for Markdown (5min)

**Success Criteria**:
- ✅ All 122 tests passing
- ✅ Multi-tab support with independent sessions
- ✅ No global mutable state
- ✅ Structured logs with request_id

**Detailed Tasks**: See [phases/pre-phase-4-refactor.md](phases/pre-phase-4-refactor.md)

---

### 📋 Phase 4: Enhanced Frontend & LLM Provider Flexibility
**Goal**: Improve UI + support multiple LLM providers (Ollama, OpenAI, Anthropic, Google)

**Status**: PLANNED (Waiting for Pre-Phase 4 completion)

**Estimated**: 17-23 hours

<details>
<summary>Checkpoints</summary>

1. Enhanced Message Rendering & Tool Visibility ✅ COMPLETE
2. LLM Provider Abstraction Layer (merge with Pre-Phase 4)
3. Provider Configuration API & Frontend UI
4. Testing, Documentation & Polish

</details>

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
