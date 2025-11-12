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

### Tasks
- [ ] **Checkpoint 1**: Data models and base client abstraction
  - [ ] Design Pydantic models: `FlightQuery`, `Flight`, `FlightResults`
  - [ ] Create abstract base class: `FlightAPIClient(ABC)`
  - [ ] Define retry decorator with circuit breaker pattern
  - [ ] Add custom exception hierarchy for API errors
  - [ ] Write unit tests for models and validators
- [ ] **Checkpoint 2**: Mock client implementation
  - [ ] Implement `MockFlightAPIClient` with realistic dummy data
  - [ ] Add flight data generation logic (varied prices, airlines, times)
  - [ ] Write unit tests for mock client
  - [ ] Verify mock client returns valid `Flight` objects
- [ ] **Checkpoint 3**: Service layer
  - [ ] Create `FlightService` class with business logic
  - [ ] Implement sorting and filtering logic
  - [ ] Add dependency injection setup (FastAPI Depends)
  - [ ] Write unit tests for service layer
- [ ] **Checkpoint 4**: LangChain tool integration
  - [ ] Create tool factory: `create_flight_search_tool(service)`
  - [ ] Integrate tool with LangChain agent (ReAct or function calling)
  - [ ] Add tool response formatting for LLM
  - [ ] Update chat service to use agent with tools
  - [ ] Add validation for tool inputs (IATA codes, dates)
  - [ ] Handle tool execution errors (return to LLM for correction)
  - [ ] Write functional tests for tool calling
- [ ] **Checkpoint 5**: E2E testing and documentation
  - [ ] E2E test: User message → Agent → Tool call → Mock API → Response
  - [ ] Test error handling paths (invalid input, API failures)
  - [ ] Test streaming with tool calls
  - [ ] Update API documentation
  - [ ] Review and refactor suggestions

**Learning Focus**: LangChain tools/agents, function calling, tool integration patterns, retry logic, circuit breakers

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
- **Current Phase**: Phase 3 - Mock Flight Search Tool (Ready to start)
- **Last Updated**: 2025-01-12
- **Blockers**: None
- **Next Steps**: 
  1. Review and finalize copilot-instructions.md
  2. Begin Phase 3 Checkpoint 1 (data models + base client abstraction)

### Completed Milestones
- ✅ Full project structure with monorepo setup (backend + frontend)
- ✅ Development tooling configured (uv, ruff, mypy, pytest, just)
- ✅ FastAPI backend with health check endpoint
- ✅ LangChain chat agent integrated with Ollama (deepseek-r1:8b)
- ✅ Session-based conversation memory working
- ✅ Streaming chat responses via Server-Sent Events
- ✅ React chat UI with Chakra UI v3, markdown rendering (tables, lists, code)
- ✅ All tests passing (6/6)
- ✅ Vite proxy configured for seamless API calls
- ✅ Copilot instructions finalized with team workflow
