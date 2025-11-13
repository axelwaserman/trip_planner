# Pre-Phase 4 Refactor: Technical Debt Resolution

**Status**: 🔄 IN PROGRESS  
**Started**: 2025-11-13  
**Estimated**: 17-23 hours over 2-3 days

## Goal
Address critical architectural issues before Phase 4 implementation.

---

## Priority 0 (Must Fix - 10-14h)

### Task 1: Session Management & Multi-Tab Support ⏱️ 3-4h
**Status**: 🔄 IN PROGRESS (see [NOW.md](../NOW.md))

**Problem**: Global `_global_chat_store` is an anti-pattern causing shared state across tabs.

**Tasks**:
- [ ] Create `ChatSession` domain model with metadata in `app/domain/session.py`
- [ ] Implement `SessionStore` ABC with `InMemorySessionStore` in `app/infrastructure/storage/session.py`
- [ ] Add session lifecycle API: `POST /api/chat/session`, `GET /api/chat/session/{session_id}`
- [ ] Refactor `ChatService` to accept session_id, remove `_global_chat_store`
- [ ] Update frontend to initialize session on mount

**Success Criteria**:
- ✅ Each browser tab creates independent session
- ✅ No global mutable state
- ✅ All tests passing

---

### Task 2: LLM Provider Abstraction Layer ⏱️ 4-5h
**Status**: ⏳ NOT STARTED

**Problem**: Hardcoded Ollama provider, can't easily switch LLMs.

**Tasks**:
- [ ] Create `LLMProvider` Protocol in `app/infrastructure/llm/base.py`:
  - Methods: `ainvoke()`, `astream()`, `bind_tools()`, `get_provider_name()`, `validate_config()`
- [ ] Implement `OllamaProvider` in `app/infrastructure/llm/ollama.py`
- [ ] Create `LLMProviderFactory` in `app/infrastructure/llm/factory.py`
- [ ] Refactor `ChatService` to accept injected provider
- [ ] Store provider choice in `ChatSession.metadata`
- [ ] Add unit tests for each provider (mock API clients)

**Success Criteria**:
- ✅ ChatService works with any provider via dependency injection
- ✅ Provider validation checks for required config
- ✅ Session-scoped provider selection

**Future**: Add OpenAI, Anthropic, Google providers in Phase 4 Checkpoint 2.

---

### Task 3: StreamEvent Inheritance (Single Responsibility) ⏱️ 2-3h
**Status**: ⏳ NOT STARTED

**Problem**: Monolithic `StreamEvent` model violates Single Responsibility Principle.

**Tasks**:
- [ ] Create event hierarchy in `app/domain/chat.py`:
  ```python
  class ContentEvent(BaseModel):
      event_type: Literal["content"]
      chunk: str
      has_thinking: bool = False
  
  class ThinkingEvent(BaseModel):
      event_type: Literal["thinking"]
      chunk: str
  
  class ToolCallEvent(BaseModel):
      event_type: Literal["tool_call"]
      metadata: ToolCallMetadata
  
  class ToolResultEvent(BaseModel):
      event_type: Literal["tool_result"]
      metadata: ToolResultMetadata
  
  class ErrorEvent(BaseModel):
      event_type: Literal["error"]
      message: str
      code: str | None = None
  
  ChatStreamEvent = ContentEvent | ThinkingEvent | ToolCallEvent | ToolResultEvent | ErrorEvent
  ```
- [ ] Update SSE serialization in `app/api/routes/chat.py`
- [ ] Update frontend parsing in `ChatInterface.tsx`
- [ ] Update all tests to use new event types

**Success Criteria**:
- ✅ Each event type has single responsibility
- ✅ Type-safe discriminated union
- ✅ Easier to add new event types

---

### Task 4: JSON Tool Output (LLM-Friendly Format) ⏱️ 1-2h
**Status**: ⏳ NOT STARTED

**Problem**: Tool returns verbose formatted strings; LLM should format naturally.

**Tasks**:
- [ ] Refactor `search_flights()` in `app/tools/flight_search.py` to return JSON:
  ```python
  {
      "status": "success",
      "query": {"origin": "JFK", "destination": "LHR", ...},
      "results": [
          {
              "flight_number": "AA100",
              "airline": "American Airlines",
              "route": "JFK → LHR",
              "departure": "2025-12-01T10:00:00Z",
              "arrival": "2025-12-01T22:00:00Z",
              "duration_hours": 7.5,
              "price_usd": 850.0,
              "stops": 0
          },
          ...
      ],
      "count": 5
  }
  ```
- [ ] Update tool docstring for JSON parsing instructions
- [ ] Remove verbose string formatting
- [ ] Update tests to validate JSON structure

**Success Criteria**:
- ✅ Tool returns structured JSON
- ✅ LLM can naturally format results
- ✅ Easier to add new fields

---

## Priority 1 (Should Fix - 5-7h)

### Task 5: Frontend State Management with useReducer ⏱️ 3-4h
**Status**: ⏳ NOT STARTED

**Problem**: Imperative state updates with index tracking, hard to reason about.

**Tasks**:
- [ ] Create `ChatAction` discriminated union in `ChatInterface.tsx`:
  ```typescript
  type ChatAction =
    | { type: 'ADD_USER_MESSAGE'; content: string }
    | { type: 'START_ASSISTANT_MESSAGE' }
    | { type: 'APPEND_CONTENT'; chunk: string }
    | { type: 'APPEND_THINKING'; chunk: string }
    | { type: 'ADD_TOOL_CALL'; metadata: ToolCallMetadata }
    | { type: 'ADD_TOOL_RESULT'; metadata: ToolResultMetadata }
    | { type: 'SET_LOADING'; isLoading: boolean }
    | { type: 'SET_ERROR'; error: string | null };
  ```
- [ ] Implement `chatReducer` with immutable updates
- [ ] Extract streaming logic into `useChatStream` custom hook
- [ ] Remove imperative index tracking
- [ ] Add unit tests for reducer

**Success Criteria**:
- ✅ Declarative state updates
- ✅ Easier to add new message types
- ✅ Better testability

---

### Task 6: Structured Logging (FastAPI Best Practices) ⏱️ 2h
**Status**: ⏳ NOT STARTED

**Problem**: No request correlation, hard to debug issues.

**Tasks**:
- [ ] Add `structlog` dependency: `uv add structlog`
- [ ] Create `RequestLoggingMiddleware` in `app/middleware/logging.py`:
  - Generate `request_id` for each request
  - Log request start/end with timing
  - Add `request_id` to all logs in request context
- [ ] Instrument `ChatService` with contextual logging:
  - Log tool calls with arguments
  - Log streaming duration
  - Log errors with full context
- [ ] Configure structured logging in `app/main.py`

**Success Criteria**:
- ✅ All logs have `request_id`
- ✅ Easy to trace requests end-to-end
- ✅ JSON-formatted logs for production

---

## Priority 2 (Quick Wins - 2-3h)

### Task 7: Pydantic Model Validators ⏱️ 30min
**Status**: ⏳ NOT STARTED

**Problem**: Missing validation for business rules.

**Tasks**:
- [ ] Add validators to `Flight` model in `app/domain/models.py`:
  ```python
  @field_validator("arrival_time")
  @classmethod
  def validate_flight_times(cls, v: datetime, info) -> datetime:
      if "departure_time" in info.data and v <= info.data["departure_time"]:
          raise ValueError("Arrival must be after departure")
      return v
  ```
- [ ] Add validator to `FlightQuery`:
  ```python
  @field_validator("departure_date")
  @classmethod
  def validate_future_date(cls, v: str) -> str:
      date = datetime.strptime(v, "%Y-%m-%d").date()
      if date < datetime.now().date():
          raise ValueError("Departure date must be in the future")
      return v
  
  @model_validator(mode="after")
  def validate_different_airports(self) -> "FlightQuery":
      if self.origin == self.destination:
          raise ValueError("Origin and destination must be different")
      return self
  ```
- [ ] Add tests for validation errors

**Success Criteria**:
- ✅ Invalid data rejected at model level
- ✅ Clear error messages

---

### Task 8: Deduplicate Test Logic ⏱️ 1-2h
**Status**: ⏳ NOT STARTED

**Problem**: Duplicate setup code across test files.

**Tasks**:
- [ ] Extract `create_mock_flight()` factory to `tests/fixtures/flights.py`:
  ```python
  def create_mock_flight(
      flight_number: str = "AA100",
      origin: str = "JFK",
      destination: str = "LHR",
      **overrides
  ) -> Flight:
      defaults = {
          "flight_number": flight_number,
          "origin": origin,
          "destination": destination,
          "departure_time": datetime.now() + timedelta(days=1),
          "arrival_time": datetime.now() + timedelta(days=1, hours=7),
          "price": 850.0,
          "airline": "American Airlines",
      }
      return Flight(**(defaults | overrides))
  ```
- [ ] Extract `parse_sse_events()` helper to `tests/utils/sse.py`:
  ```python
  async def parse_sse_events(response: httpx.Response) -> list[dict]:
      events = []
      async for line in response.aiter_lines():
          if line.startswith("data: "):
              events.append(json.loads(line[6:]))
      return events
  ```
- [ ] Refactor tests to use shared fixtures

**Success Criteria**:
- ✅ No duplicate factory code
- ✅ Easier to maintain tests

---

### Task 9: Fix Dependency Injection Pattern ⏱️ 30min
**Status**: ⏳ NOT STARTED

**Problem**: Using `@lru_cache` for singletons violates DI pattern.

**Tasks**:
- [ ] Remove `@lru_cache` from dependency factories
- [ ] Use FastAPI `lifespan` context manager in `app/main.py`:
  ```python
  from contextlib import asynccontextmanager
  
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup: Create singletons
      app.state.flight_client = MockFlightAPIClient()
      app.state.session_store = InMemorySessionStore()
      yield
      # Shutdown: Cleanup
      await app.state.session_store.cleanup_expired()
  
  app = FastAPI(lifespan=lifespan)
  ```
- [ ] Update dependency factories to use `app.state`:
  ```python
  from fastapi import Request
  
  def get_flight_client(request: Request) -> FlightAPIClient:
      return request.app.state.flight_client
  ```

**Success Criteria**:
- ✅ Proper singleton lifecycle
- ✅ Follows FastAPI best practices

---

### Task 10: XSS Protection for Markdown ⏱️ 5min
**Status**: ⏳ NOT STARTED

**Problem**: ReactMarkdown doesn't sanitize HTML by default.

**Tasks**:
- [ ] Install `rehype-sanitize`: `npm install rehype-sanitize`
- [ ] Add to `ReactMarkdown` in `ChatInterface.tsx`:
  ```typescript
  import rehypeSanitize from 'rehype-sanitize';
  
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    rehypePlugins={[rehypeSanitize]}
  >
    {content}
  </ReactMarkdown>
  ```

**Success Criteria**:
- ✅ Malicious HTML stripped from markdown

---

## Done Criteria

- ✅ All 122 tests passing
- ✅ `just typecheck` passes (no type errors)
- ✅ Multi-tab support: Each browser tab has independent session
- ✅ Structured logs with request_id correlation
- ✅ No global mutable state in codebase
- ✅ `ChatService.chat()` removed (streaming only)

---

## Notes

**Delete this file after completion** - move completed work summary to ROADMAP.md.
