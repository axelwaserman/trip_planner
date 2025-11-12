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

### Checkpoint 1: Enhanced Message Rendering & Tool Visibility
**Goal**: Make tool execution visible and improve overall chat UX

**Architecture**: Message-Based Approach (Option 2)
- Tool calls and results are separate messages in chat history
- Expandable/collapsible tool result cards with full details
- Mobile-first responsive design

#### Backend Tasks
- [ ] **Update domain models** (`app/domain/chat.py`):
  - [ ] Add `MessageType` enum: `user`, `assistant`, `tool_call`, `tool_result`
  - [ ] Extend `ChatRequest` to support typed messages
  - [ ] Create `ToolCallMetadata` model (tool name, arguments, started_at, completed_at)
  - [ ] Create `ToolResultMetadata` model (tool name, summary, full result, status)
  
- [ ] **Update SSE streaming** (`app/api/routes/chat.py`):
  - [ ] Emit separate events for tool call start: `{"type": "tool_call", "tool_name": "search_flights", "arguments": {...}}`
  - [ ] Emit tool execution status updates: `{"type": "tool_status", "status": "executing"}`
  - [ ] Emit tool result as separate message: `{"type": "tool_result", "summary": "...", "full_result": "..."}`
  - [ ] Continue streaming assistant response after tool execution
  
- [ ] **Update ChatService** (`app/chat.py`):
  - [ ] Track tool execution timing (start/end timestamps)
  - [ ] Generate summary for tool results (first 2-3 lines of formatted output)
  - [ ] Store tool call and result messages in conversation history
  - [ ] Ensure message history includes all message types for context

#### Frontend Tasks
- [ ] **Update Message interface** (`ChatInterface.tsx`):
  ```tsx
  interface Message {
    role: 'user' | 'assistant' | 'tool_call' | 'tool_result'
    content: string
    metadata?: {
      toolName?: string
      arguments?: Record<string, any>
      summary?: string
      fullResult?: string
      status?: 'executing' | 'complete' | 'error'
      elapsedMs?: number
      startedAt?: string
      completedAt?: string
    }
  }
  ```

- [ ] **Create `ToolCallCard` component**:
  - [ ] Show tool icon (✈️ for flights) + tool name
  - [ ] Display status indicator (spinner when executing, checkmark when complete)
  - [ ] Show elapsed time
  - [ ] Expandable section showing tool arguments (e.g., "JFK → LAX, 2025-12-15")
  - [ ] Mobile-optimized (collapsible by default on small screens)

- [ ] **Create `ToolResultCard` component**:
  - [ ] Collapsed by default, showing only summary
  - [ ] Dropdown/chevron icon to expand full results
  - [ ] Full results shown in scrollable container with markdown rendering
  - [ ] "View on site" button/link support (for future external links)
  - [ ] Copy button to copy full results to clipboard
  - [ ] Mobile-friendly accordion pattern

- [ ] **Enhanced loading states**:
  - [ ] Replace "Thinking..." with animated typing indicator (three dots)
  - [ ] Show context-aware status: "Analyzing your request..." → "Searching flights..." → "Processing results..."
  - [ ] Smooth transitions between states

- [ ] **Message rendering logic**:
  - [ ] Separate rendering functions per message type
  - [ ] User messages: Right-aligned, blue background
  - [ ] Assistant messages: Left-aligned, white background, markdown support
  - [ ] Tool call messages: `<ToolCallCard>` component
  - [ ] Tool result messages: `<ToolResultCard>` component

- [ ] **Mobile responsiveness**:
  - [ ] Test on 320px, 375px, 768px viewports
  - [ ] Tool cards stack vertically on mobile
  - [ ] Adjust font sizes and padding for mobile
  - [ ] Ensure dropdowns/accordions work on touch devices
  - [ ] Test markdown table horizontal scroll
  - [ ] Sticky input area at bottom

#### Testing Tasks
- [ ] **Unit tests**:
  - [ ] Test `ToolCallCard` rendering with different statuses
  - [ ] Test `ToolResultCard` expand/collapse functionality
  - [ ] Test message parsing logic for different SSE event types

- [ ] **Manual tests**:
  - [ ] Ask for flight search, verify tool call card appears with spinner
  - [ ] Verify tool result card shows collapsed summary by default
  - [ ] Click to expand full results, verify markdown renders correctly
  - [ ] Test on Chrome DevTools mobile viewport (iPhone, Android)
  - [ ] Verify message history maintains all tool calls/results after refresh

**Success Criteria**: 
- ✅ Tool execution is clearly visible with dedicated message cards
- ✅ Tool arguments are visible in expandable dropdown
- ✅ Tool results are collapsible with summary preview
- ✅ Loading states provide context-aware feedback
- ✅ UI works smoothly on mobile devices (320px+)
- ✅ All message types persist in conversation history

---

### Checkpoint 2: LLM Provider Abstraction Layer
**Goal**: Create flexible backend that supports multiple LLM providers

#### Architecture Overview
```
BaseLLMProvider (ABC)
├── OllamaProvider (current)
├── OpenAIProvider (gpt-4o, gpt-4o-mini)
├── AnthropicProvider (claude-3.5-sonnet, claude-3-opus)
└── GoogleProvider (gemini-1.5-pro, gemini-1.5-flash)
```

#### Tasks
- [ ] **Create provider abstraction**:
  - [ ] Create `app/infrastructure/llm/base.py` with `BaseLLMProvider` ABC:
    ```python
    class BaseLLMProvider(ABC):
        @abstractmethod
        async def create_chat_model(self, **kwargs) -> BaseChatModel:
            """Return LangChain ChatModel instance with tools bound."""
        
        @abstractmethod
        def get_provider_name(self) -> str:
            """Return provider name (e.g., 'ollama', 'openai')."""
        
        @abstractmethod
        def get_available_models(self) -> list[str]:
            """Return list of supported models."""
        
        @abstractmethod
        def validate_config(self) -> bool:
            """Check if provider is properly configured (API keys, etc.)."""
    ```

- [ ] **Implement provider classes**:
  - [ ] `OllamaProvider` in `app/infrastructure/llm/ollama.py`:
    - Uses existing `langchain_ollama.ChatOllama`
    - Configuration from `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
    - No API key required
    - Models: List from `ollama list` (qwen3:8b, qwen2.5:7b, deepseek-r1:8b, etc.)
  
  - [ ] `OpenAIProvider` in `app/infrastructure/llm/openai.py`:
    - Install: `uv add langchain-openai`
    - Uses `langchain_openai.ChatOpenAI`
    - Configuration: `OPENAI_API_KEY`
    - Models: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo
  
  - [ ] `AnthropicProvider` in `app/infrastructure/llm/anthropic.py`:
    - Install: `uv add langchain-anthropic`
    - Uses `langchain_anthropic.ChatAnthropic`
    - Configuration: `ANTHROPIC_API_KEY`
    - Models: claude-3-5-sonnet-20241022, claude-3-opus-20240229, claude-3-haiku-20240307
  
  - [ ] `GoogleProvider` in `app/infrastructure/llm/google.py`:
    - Install: `uv add langchain-google-genai`
    - Uses `langchain_google_genai.ChatGoogleGenerativeAI`
    - Configuration: `GOOGLE_API_KEY`
    - Models: gemini-1.5-pro, gemini-1.5-flash, gemini-1.0-pro

- [ ] **Provider factory**:
  - [ ] Create `app/infrastructure/llm/factory.py` with `LLMProviderFactory`:
    ```python
    class LLMProviderFactory:
        _providers: dict[str, type[BaseLLMProvider]] = {
            "ollama": OllamaProvider,
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "google": GoogleProvider,
        }
        
        @classmethod
        def create_provider(cls, provider_name: str) -> BaseLLMProvider:
            """Create provider instance by name."""
        
        @classmethod
        def get_available_providers(cls) -> list[dict[str, Any]]:
            """Return list of providers with their config status."""
    ```

- [ ] **Update Settings**:
  - [ ] Add to `app/config.py`:
    ```python
    # LLM Provider Configuration
    llm_provider: str = "ollama"  # Default to Ollama
    
    # Ollama (existing)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    
    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    
    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    
    # Google
    google_api_key: str | None = None
    google_model: str = "gemini-1.5-flash"
    ```
  
  - [ ] Update `.env.example` with new variables

- [ ] **Refactor ChatService**:
  - [ ] Update `ChatService.__init__` to accept `BaseLLMProvider` instead of hardcoding Ollama:
    ```python
    def __init__(self, flight_service: FlightService, llm_provider: BaseLLMProvider):
        self.store = _global_chat_store
        flight_search_func = create_flight_search_tool(flight_service)
        self.search_flights_tool = tool(flight_search_func)
        
        # Get chat model from provider
        chat_model = await llm_provider.create_chat_model(temperature=0.7)
        self.llm = chat_model.bind_tools([self.search_flights_tool])
    ```
  
  - [ ] Update `create_chat_service` factory to use provider from settings

- [ ] **Testing**:
  - [ ] Unit tests for each provider (mock API clients)
  - [ ] Test provider factory creation and validation
  - [ ] Integration test: Create ChatService with each provider
  - [ ] E2E test: Send message using different providers (mock API responses)

**Success Criteria**:
- ✅ All four providers implemented and tested
- ✅ ChatService works with any provider via dependency injection
- ✅ Provider validation checks for required API keys
- ✅ Tests pass with mocked provider responses

---

### Checkpoint 3: Provider Configuration API & Frontend UI
**Goal**: Allow users to select and configure LLM providers via UI

#### Backend Tasks
- [ ] **Provider configuration endpoints**:
  - [ ] `GET /api/llm/providers` - List available providers with status:
    ```json
    {
      "providers": [
        {
          "name": "ollama",
          "display_name": "Ollama (Local)",
          "is_configured": true,
          "available_models": ["qwen3:8b", "qwen2.5:7b", "deepseek-r1:8b"],
          "current_model": "qwen3:8b"
        },
        {
          "name": "openai",
          "display_name": "OpenAI",
          "is_configured": false,
          "available_models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
          "requires_api_key": true
        }
      ],
      "current_provider": "ollama"
    }
    ```
  
  - [ ] `POST /api/llm/configure` - Update provider settings:
    ```json
    {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "api_key": "sk-..." // Optional, can be env var
    }
    ```
  
  - [ ] `GET /api/llm/current` - Get current provider and model info

- [ ] **Session-based configuration** (optional):
  - [ ] Allow per-session provider override (don't persist globally)
  - [ ] Store provider choice in session metadata
  - [ ] Useful for testing multiple providers simultaneously

#### Frontend Tasks
- [ ] **Settings Panel Component**:
  - [ ] Create `SettingsPanel.tsx` component with:
    - Provider dropdown/radio group
    - Model selection dropdown (filtered by provider)
    - API key input (for external providers)
    - "Test Connection" button
    - Save/Cancel buttons
  
  - [ ] Add settings icon/button to header (⚙️)
  - [ ] Open settings in modal or slide-out drawer
  - [ ] Fetch providers on mount: `GET /api/llm/providers`
  - [ ] Submit configuration: `POST /api/llm/configure`

- [ ] **Provider status indicators**:
  - [ ] Show current provider/model in chat header (e.g., "💬 Ollama • qwen3:8b")
  - [ ] Add tooltip on hover with provider details
  - [ ] Show warning if provider is unconfigured

- [ ] **API key management**:
  - [ ] Add secure input field for API keys (type="password")
  - [ ] Option to store in browser localStorage (warn about security)
  - [ ] Option to use environment variables (recommended)
  - [ ] Validate API key format before saving

- [ ] **Testing**:
  - [ ] Manual test: Switch from Ollama to OpenAI (if API key available)
  - [ ] Manual test: Verify model dropdown updates when provider changes
  - [ ] Manual test: Test API key validation and error messages
  - [ ] Manual test: Send message after switching providers

**Success Criteria**:
- ✅ Users can view available providers and their configuration status
- ✅ Users can switch providers and models via UI
- ✅ API keys can be entered and validated
- ✅ Current provider is clearly displayed in chat interface
- ✅ Settings persist across sessions (via backend config)

---

### Checkpoint 4: Testing, Documentation & Polish
**Goal**: Ensure production-ready quality for Phase 4 features

#### Tasks
- [ ] **Comprehensive testing**:
  - [ ] Add unit tests for all new components (`ToolCallIndicator`, `SettingsPanel`)
  - [ ] Add integration tests for provider endpoints
  - [ ] Test mobile responsiveness on real devices (iOS Safari, Android Chrome)
  - [ ] Test markdown rendering with all new UI components
  - [ ] Performance test: Measure latency with different providers
  - [ ] Load test: Multiple concurrent sessions with different providers

- [ ] **Error handling**:
  - [ ] Handle API key validation errors gracefully
  - [ ] Show user-friendly messages for provider failures (rate limits, network errors)
  - [ ] Add retry logic for transient provider failures
  - [ ] Fallback to Ollama if external provider fails

- [ ] **Documentation updates**:
  - [ ] Update `README.md` with:
    - LLM provider setup instructions
    - How to get API keys for OpenAI/Anthropic/Google
    - Environment variable configuration
    - Provider comparison table (cost, latency, capabilities)
  - [ ] Add `docs/LLM_PROVIDERS.md` with detailed provider guide
  - [ ] Update API documentation (OpenAPI/Swagger) with new endpoints
  - [ ] Add architecture diagrams showing provider abstraction layer

- [ ] **Code quality**:
  - [ ] Run `just fix` and `just typecheck` on all new code
  - [ ] Ensure test coverage >80% for new modules
  - [ ] Add docstrings to all provider classes and methods
  - [ ] Review and refactor for consistency

- [ ] **User experience polish**:
  - [ ] Add loading skeletons for provider list
  - [ ] Add success/error toasts for configuration changes
  - [ ] Improve error messages (avoid technical jargon)
  - [ ] Add keyboard shortcuts (e.g., Ctrl+, for settings)
  - [ ] Add dark mode support (optional, but nice to have)

**Success Criteria**:
- ✅ All tests pass (unit, integration, E2E)
- ✅ Code quality checks pass (ruff, mypy)
- ✅ Documentation is comprehensive and up-to-date
- ✅ UI is polished and user-friendly
- ✅ Error handling is robust and helpful

---

## Phase 4 Summary

**Status**: 🔄 **IN PROGRESS** (Not Started)

**Key Deliverables**:
1. ✨ Enhanced chat UI with tool execution visibility
2. 🔌 Multi-provider LLM support (Ollama, OpenAI, Anthropic, Google)
3. ⚙️ User-facing settings panel for provider configuration
4. 📱 Mobile-responsive design
5. 📚 Comprehensive documentation for provider setup

**Estimated Effort**: 
- Checkpoint 1: 4-6 hours (UI enhancements)
- Checkpoint 2: 6-8 hours (Provider abstraction)
- Checkpoint 3: 4-5 hours (Configuration UI)
- Checkpoint 4: 3-4 hours (Testing & docs)
- **Total**: ~17-23 hours

**Dependencies**:
- OpenAI API key (optional, for testing)
- Anthropic API key (optional, for testing)
- Google API key (optional, for testing)

**Learning Focus**: 
- React component design patterns (indicators, settings panels)
- LangChain provider abstraction and dependency injection
- Multi-provider LLM integration and testing
- API key management and security best practices
- Mobile-first responsive design

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
