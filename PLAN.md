# Trip Planner - Implementation Plan

## Project Goal
Build an AI-powered trip planning chat agent that can leverage real-world APIs to provide up-to-date travel options.

## MVP Scope
- Conversational AI agent for trip planning
- Stateless (single session, no database, no auth)
- One functional tool: Flight search (mocked initially)
- REST API backend
- React + TypeScript frontend

## Tech Stack
- **Backend**: FastAPI, LangChain, Python 3.13
- **Frontend**: React, TypeScript, Chakra UI v3
- **Tooling**: uv, ruff, mypy, pytest, just
- **LLM**: Ollama (local, deepseek-r1:8b model)

---

## Phase 1: Foundation & Basic FastAPI Setup
**Goal**: Get project structure with proper tooling, basic FastAPI server running

### Tasks
- [x] Initialize Python project with uv
- [x] Set up project structure (app/, tests/, config)
- [x] Configure ruff for linting (consolidated in pyproject.toml)
- [x] Configure mypy for type checking
- [x] Create basic FastAPI app with health check endpoint
- [x] Set up pytest with first basic test
- [x] Add environment variable management (.env.example)
- [x] Create README with setup instructions
- [x] Add .gitignore
- [x] Initialize frontend with Vite + React + TypeScript
- [x] Install and configure Chakra UI v3
- [x] Configure Vite proxy for API calls
- [x] Install backend dependencies with uv
- [x] Run backend server and verify health endpoint works
- [x] Run frontend and verify it loads
- [x] Run tests and verify they pass (6/6 passing)
- [x] Add justfile for common development commands
- [x] Frontend health check displays backend connection status

**Learning Focus**: Project structure, modern Python tooling, FastAPI basics, monorepo setup

**Status**: ✅ COMPLETED

---

## Phase 2: LangChain Integration & Chat Agent
**Goal**: Create working chat agent with LangChain and Ollama

### Tasks
- [x] Install langchain, langchain-ollama, and related dependencies
- [x] Configure Ollama connection settings (base URL, model selection)
- [x] Create chat service with LangChain's RunnableWithMessageHistory
- [x] Implement session-based conversation memory using InMemoryChatMessageHistory
- [x] Add chat endpoint to FastAPI (/api/chat)
- [x] Write tests for chat functionality with mocking
- [x] Build chat UI component in React
- [x] Connect frontend to chat endpoint
- [x] Test full conversation flow (frontend → backend → Ollama → response)
- [x] Add streaming endpoint (/api/chat/stream) using Server-Sent Events
- [x] Implement streaming on frontend with ReadableStream
- [x] Add markdown rendering with react-markdown + remark-gfm
- [x] Style markdown tables, lists, and code blocks
- [x] Optimize model selection (switched from gpt-oss:20b to deepseek-r1:8b)

**Learning Focus**: LangChain 1.0 patterns, async streaming, conversation memory, SSE, markdown rendering

**Status**: ✅ COMPLETED

---

## Phase 3: Mock Flight Search Tool
**Goal**: Agent can call a flight search tool and incorporate results into conversation

### Important: LangChain 1.0 Patterns
This phase uses **LangChain 1.0** (installed: `langchain==1.0.3`):
- ✅ Use `create_agent()` from `langchain.agents` (NOT `langchain_classic`)
- ✅ Tools are **plain Python functions** (no decorators needed)
- ✅ Agent built on LangGraph (requires `langgraph` dependency)
- ✅ Async-first for all I/O operations
- ✅ Support concurrent tool calls (multiple LLMs/tools)

### Tasks
- [x] **Checkpoint 1**: Data models and base client abstraction
  - [x] Design Pydantic models: `FlightQuery` ✅, `Flight` ✅ (existing in `domain/models.py`)
  - [x] Create abstract base class: `FlightAPIClient(ABC)` ✅ (existing in `infrastructure/clients/flight.py`)
  - [x] Define retry decorator with circuit breaker pattern (`app/utils/retry.py`)
  - [x] Add custom exception hierarchy for API errors (`app/exceptions.py`)
  - [x] Write unit tests for retry decorator and exceptions
  - [x] Update existing model tests if needed
- [x] **Checkpoint 2**: Mock client implementation
  - [x] Install `langgraph` dependency (required by LangChain 1.0 agents)
  - [x] Implement `MockFlightAPIClient` in `infrastructure/clients/mock.py`
  - [x] Add realistic flight data generation (varied prices, airlines, times, layovers)
  - [x] Implement all abstract methods: `search()`, `get_flight_details()`, `check_availability()`, `health_check()`
  - [x] Write comprehensive unit tests in `tests/test_mock_client.py`
  - [x] Run quality checks: `just fix` → `just typecheck` → `just test`
- [x] **Checkpoint 3**: Service layer with dependency injection
  - [x] Create `FlightService` in `services/flight.py` with async methods
  - [x] Implement business logic: sorting (price/duration/time), filtering, pagination
  - [x] Create FastAPI dependency factory: `get_flight_client()` → `MockFlightAPIClient`
  - [x] Add flights endpoint: `POST /api/flights/search` in `api/routes/flights.py`
  - [x] Write unit tests for service (mock client, test business logic)
  - [x] Write integration tests for endpoint (TestClient)
  - [x] Update `main.py` to include flights router
- [x] **Checkpoint 4**: LangChain 1.0 agent integration (NON-STREAMING)
  - [x] Create plain Python function tool in `tools/flight_search.py`:
    - Takes primitive types (str, int, bool) not Pydantic models
    - Clear docstring describing when/how LLM should use it
    - Returns formatted string (readable by LLM)
    - Handles ValidationError → returns error message to LLM
  - [x] Update `ChatService` to use `bind_tools()`:
    - Uses LangChain 1.0 `bind_tools()` pattern (not `create_agent()`)
    - Inject `FlightService` via constructor
    - Define tool function with `@tool` decorator
    - Agent supports tool calls with `llm.bind_tools()`
  - [x] Implement **non-streaming** agent responses first:
    - Use `llm.invoke()` with message history
    - Convert session history to messages format
    - Return complete response (may include tool call metadata)
  - [x] Write unit tests: mock service, test tool function, test agent flow
  - [x] Write integration tests: full chat with tool calling
  - [x] Manual testing via frontend (verify tool calls work)
- [x] **Checkpoint 5**: Streaming support and E2E testing
  - [x] Add streaming agent responses:
    - Use `llm.astream()` for chunk-by-chunk streaming
    - Handle different chunk types (content, tool_calls, etc.)
    - Update SSE endpoint to stream agent chunks
  - [x] Write E2E tests in `tests/test_e2e.py` and `tests/test_e2e_manual.py`:
    - User message → Agent → Tool call → Mock API → Response
    - Multi-turn conversations with tool calls
    - Error paths: invalid IATA codes, API failures, validation errors
    - Streaming with tool execution
  - [ ] Update API documentation (OpenAPI/Swagger) - Deferred to Phase 6
  - [ ] Update README with architecture overview - Deferred to Phase 6
  - [x] Run full test suite and quality checks
  - [x] Review and refactor suggestions

**Status**: ✅ **COMPLETE** (122/122 tests passing)

**Implementation Notes**:
- Model upgraded to `qwen3:8b` (better reasoning + tool calling support)
- Uses `bind_tools()` pattern with `@tool` decorator (LangChain 1.0)
- Global `_global_chat_store` for conversation memory across requests
- Streaming with `llm.astream()` for real-time chunk delivery
- Route display added: shows "JFK → LHR" format in flight results
- 13 E2E tests covering tool calling, memory, streaming, error handling

**Learning Focus**: LangChain 1.0 agent patterns, plain function tools, async tool execution, streaming responses, conversation memory management

---

## Phase 4: Enhanced Frontend & LLM Provider Flexibility
**Goal**: Improve UI to show tool usage + support multiple LLM providers

### Tasks
- [ ] Display tool usage in chat (show when agent searches flights)
- [ ] Add loading states for tool execution
- [ ] Improve message rendering (tool calls, results, thinking)
- [ ] Make UI responsive for mobile
- [ ] Add LLM provider selection UI (dropdown or config)
- [ ] Create generic LLM provider wrapper/factory
  - [ ] Support Ollama (local)
  - [ ] Support Gemini (API key via UI or env var)
  - [ ] Support OpenAI (API key via UI or env var)
  - [ ] Support Anthropic (API key via UI or env var)
- [ ] Add LLM provider configuration to backend settings
- [ ] Test switching between providers
- [ ] Update documentation for multi-provider setup

**Learning Focus**: React UI patterns, LLM provider abstraction, configuration management

---

## Phase 5: Enhanced Flight Tool & Real API Integration
**Goal**: Replace mock with real Amadeus API integration

### Tasks
- [ ] Set up Amadeus API credentials
- [ ] Create Amadeus client wrapper
- [ ] Implement async flight search using Amadeus API
- [ ] Add rate limiting/caching to avoid API abuse
- [ ] Update tool to use real API instead of mock
- [ ] Add comprehensive error handling (API failures, rate limits)
- [ ] Test with real flight searches
- [ ] Add retry logic for transient failures

**Learning Focus**: External API integration, async HTTP clients, error handling, rate limiting

---

## Phase 6: Polish & Production Readiness
**Goal**: Make MVP production-ready

### Tasks
- [ ] Add comprehensive logging
- [ ] Set up proper configuration management
- [ ] Add API documentation (OpenAPI/Swagger)
- [ ] Improve test coverage (aim for >80% critical paths)
- [ ] Add Docker setup for easy deployment
- [ ] Create deployment guide
- [ ] Add conversation cost tracking (LLM API usage)
- [ ] Performance optimization (response streaming?)
- [ ] Security review (API keys, input validation)

**Learning Focus**: Production best practices, deployment, monitoring

---

## Future Enhancements (Post-MVP)
These are ideas to explore after MVP is working:

### Database & Persistence
- [ ] Add PostgreSQL for conversation history
- [ ] User authentication (JWT)
- [ ] Save trip plans
- [ ] User preferences

### GraphQL Layer
- [ ] Migrate to GraphQL API
- [ ] Add GraphQL subscriptions for streaming responses
- [ ] Implement complex queries for trip data

### Additional Tools
- [ ] Hotel search tool (Booking.com API)
- [ ] Restaurant recommendations (Yelp/Google Places)
- [ ] Weather information
- [ ] Currency conversion
- [ ] Activity suggestions

### DSPy Integration
- [ ] Evaluate DSPy for prompt optimization
- [ ] Use DSPy for agent reasoning improvements
- [ ] A/B test DSPy vs LangChain approaches

### Advanced Features
- [ ] Multi-turn trip planning workflows
- [ ] Budget optimization
- [ ] Itinerary generation
- [ ] Export trips (PDF, calendar)
- [ ] Multi-city trip support
- [ ] Collaborative trip planning

---

## Current Status
- **Current Phase**: Phase 3 - Mock Flight Search Tool ✅ **COMPLETE**
- **Last Updated**: 2025-11-12
- **Blockers**: None
- **Next Steps**: 
  1. Begin Phase 4 - Enhanced Frontend & LLM Provider Flexibility
  2. Display tool usage indicators in frontend UI
  3. Add LLM provider abstraction for Gemini/OpenAI/Anthropic support

### Completed Milestones
- ✅ Full project structure with monorepo setup (backend + frontend)
- ✅ Development tooling configured (uv, ruff, mypy, pytest, just)
- ✅ FastAPI backend with health check endpoint
- ✅ LangChain chat agent integrated with Ollama (qwen3:8b - supports tools)
- ✅ Session-based conversation memory with global store pattern
- ✅ **Streaming chat responses via Server-Sent Events with tool calling**
- ✅ React chat UI with Chakra UI v3, markdown rendering (tables, lists, code)
- ✅ **Mock flight search tool fully integrated with LangChain agent**
- ✅ **122/122 tests passing** (109 unit/integration + 13 E2E tests)
- ✅ Vite proxy configured for seamless API calls
- ✅ **Complete flight search workflow: query → tool call → mock API → formatted response with route display**
- ✅ **Multi-client session support with independent conversation histories**
