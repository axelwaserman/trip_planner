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
- **Frontend**: React, TypeScript, Tailwind CSS
- **Tooling**: uv, ruff, mypy, pytest
- **LLM**: Ollama (local, gpt-oss20b model)

---

## Phase 1: Foundation & Basic FastAPI Setup
**Goal**: Get project structure with proper tooling, basic FastAPI server running

### Tasks
- [ ] Initialize Python project with uv
- [ ] Set up project structure (src/, tests/, config)
- [ ] Configure ruff for linting
- [ ] Configure mypy for type checking
- [ ] Create basic FastAPI app with health check endpoint
- [ ] Set up pytest with first basic test
- [ ] Add environment variable management (.env)
- [ ] Create README with setup instructions
- [ ] Add .gitignore

**Learning Focus**: Project structure, modern Python tooling, FastAPI basics

---

## Phase 2: LangChain Chat Agent (No Tools)
**Goal**: Simple conversational agent without tools - baseline chat experience

### Tasks
- [ ] Install LangChain dependencies
- [ ] Create chat endpoint (POST /api/chat)
- [ ] Implement basic LangChain conversation chain
- [ ] Add conversation memory (in-memory for single session)
- [ ] Create request/response models (Pydantic)
- [ ] Add error handling for LLM API calls
- [ ] Write tests for chat endpoint
- [ ] Add async patterns for LLM calls
- [ ] Configure LLM provider (Ollama with gpt-oss20b model)
- [ ] Test conversation flow end-to-end

**Learning Focus**: LangChain basics, async FastAPI, conversation memory, error handling

---

## Phase 3: Mock Flight Search Tool
**Goal**: Agent can call a flight search tool and incorporate results into conversation

### Tasks
- [ ] Design flight search tool interface (inputs: origin, destination, dates)
- [ ] Create mock flight search function (returns realistic dummy data)
- [ ] Integrate tool with LangChain agent (function calling)
- [ ] Update agent to use ReAct or OpenAI Functions pattern
- [ ] Add tool response formatting
- [ ] Test agent's tool calling behavior
- [ ] Add validation for tool inputs
- [ ] Handle tool execution errors gracefully

**Learning Focus**: LangChain tools/agents, function calling, tool integration patterns

---

## Phase 4: Basic React Frontend
**Goal**: Functional chat UI that connects to backend

### Tasks
- [ ] Initialize React + TypeScript project (Vite)
- [ ] Set up Tailwind CSS
- [ ] Create chat interface component
- [ ] Implement message list with user/agent messages
- [ ] Add input field and send functionality
- [ ] Connect to FastAPI backend (fetch/axios)
- [ ] Add loading states
- [ ] Basic error handling in UI
- [ ] Display tool usage in chat (show when agent searches flights)
- [ ] Make it responsive

**Learning Focus**: React basics, TypeScript, API integration, Tailwind

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
**Phase**: Not started
**Last Updated**: 2025-11-01

### Completed Milestones
- ✅ Project initialized
- ✅ Copilot instructions defined

### Next Up
- Phase 1: Foundation & Basic FastAPI Setup
