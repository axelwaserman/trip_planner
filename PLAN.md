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
- [ ] **Checkpoint 1**: Data models and base client abstraction
  - [x] Design Pydantic models: `FlightQuery` ✅, `Flight` ✅ (existing in `domain/models.py`)
  - [x] Create abstract base class: `FlightAPIClient(ABC)` ✅ (existing in `infrastructure/clients/flight.py`)
  - [ ] Define retry decorator with circuit breaker pattern (`app/utils/retry.py`)
  - [ ] Add custom exception hierarchy for API errors (`app/exceptions.py`)
  - [ ] Write unit tests for retry decorator and exceptions
  - [ ] Update existing model tests if needed
- [ ] **Checkpoint 2**: Mock client implementation
  - [ ] Install `langgraph` dependency (required by LangChain 1.0 agents)
  - [ ] Implement `MockFlightAPIClient` in `infrastructure/clients/mock.py`
  - [ ] Add realistic flight data generation (varied prices, airlines, times, layovers)
  - [ ] Implement all abstract methods: `search()`, `get_flight_details()`, `check_availability()`, `health_check()`
  - [ ] Write comprehensive unit tests in `tests/test_mock_client.py`
  - [ ] Run quality checks: `just fix` → `just typecheck` → `just test`
- [ ] **Checkpoint 3**: Service layer with dependency injection
  - [ ] Create `FlightService` in `services/flight.py` with async methods
  - [ ] Implement business logic: sorting (price/duration/time), filtering, pagination
  - [ ] Create FastAPI dependency factory: `get_flight_client()` → `MockFlightAPIClient`
  - [ ] Add flights endpoint: `POST /api/flights/search` in `api/routes/flights.py`
  - [ ] Write unit tests for service (mock client, test business logic)
  - [ ] Write integration tests for endpoint (TestClient)
  - [ ] Update `main.py` to include flights router
- [ ] **Checkpoint 4**: LangChain 1.0 agent integration (NON-STREAMING)
  - [ ] Create plain Python function tool in `tools/flight_search.py`:
    - Takes primitive types (str, int, bool) not Pydantic models
    - Clear docstring describing when/how LLM should use it
    - Returns formatted string (readable by LLM)
    - Handles ValidationError → returns error message to LLM
  - [ ] Update `ChatService` to use `create_agent()`:
    - Import from `langchain.agents` (NOT `langchain_classic`)
    - Inject `FlightService` via constructor
    - Define tool function in `__init__` (closure over service)
    - Agent supports concurrent tool calls
  - [ ] Implement **non-streaming** agent responses first:
    - Use `agent.invoke()` with message history
    - Convert session history to messages format
    - Return complete response (may include tool call metadata)
  - [ ] Write unit tests: mock service, test tool function, test agent flow
  - [ ] Write integration tests: full chat with tool calling
  - [x] Manual testing via frontend (verify tool calls work)
- [x] **Checkpoint 5**: Streaming support and E2E testing
  - [x] Add streaming agent responses:
    - Use `llm.astream()` for chunk-by-chunk streaming
    - Handle different chunk types (content, tool_calls, etc.)
    - Update SSE endpoint to stream agent chunks
  - [x] Write E2E tests in `tests/test_e2e.py`:
    - User message → Agent → Tool call → Mock API → Response
    - Multi-turn conversations with tool calls
    - Error paths: invalid IATA codes, API failures, validation errors
    - Streaming with tool execution
  - [ ] Update API documentation (OpenAPI/Swagger) - Optional, can be done in Phase 6
  - [ ] Update README with architecture overview - Optional, can be done in Phase 6
  - [x] Run full test suite and quality checks
  - [x] Review and refactor suggestions

**Status**: ✅ **COMPLETE** (122/122 tests passing)

**Note**: Model changed to `qwen2.5:3b` (supports tool calling). Restart backend server for manual testing:
```bash
cd backend && uv run fastapi dev app/main.py
```

**Learning Focus**: LangChain 1.0 agent patterns, plain function tools, async tool execution, concurrent tool calls, streaming with LangGraph

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
- **Last Updated**: 2025-01-12
- **Blockers**: None
- **Next Steps**: 
  1. **Restart backend server** with `qwen2.5:3b` model for manual testing
  2. Test tool calling via frontend: "Find flights from LAX to JFK on June 1st 2025"
  3. Begin Phase 4 - Enhanced Frontend & LLM Provider Flexibility

### Completed Milestones
- ✅ Full project structure with monorepo setup (backend + frontend)
- ✅ Development tooling configured (uv, ruff, mypy, pytest, just)
- ✅ FastAPI backend with health check endpoint
- ✅ LangChain chat agent integrated with Ollama (qwen2.5:3b - supports tools)
- ✅ Session-based conversation memory working
- ✅ **Streaming chat responses via Server-Sent Events with tool calling**
- ✅ React chat UI with Chakra UI v3, markdown rendering (tables, lists, code)
- ✅ **Mock flight search tool fully integrated with LangChain agent**
- ✅ **122/122 tests passing** (including 13 E2E tests)
- ✅ Vite proxy configured for seamless API calls
- ✅ **Complete flight search workflow: query → tool call → mock API → formatted response**
