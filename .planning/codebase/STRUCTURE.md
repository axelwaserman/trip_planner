# Codebase Structure

> Mapped: 2026-04-27

## Directory Layout

```
trip_planner/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   ├── main.py              # FastAPI app entry point, lifespan, CORS
│   │   │   └── routes/
│   │   │       ├── auth.py           # OAuth2 auth routes (dummy/placeholder)
│   │   │       └── routes.py         # Chat + session API routes
│   │   ├── chat.py                   # ChatService - LangChain streaming + tool calling
│   │   ├── config.py                 # Settings via pydantic-settings
│   │   ├── exceptions.py             # Custom exception hierarchy
│   │   ├── models.py                 # Pydantic models (Flight, StreamEvent, etc.)
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── flight_client.py      # FlightAPIClient + MockFlightAPIClient
│   │       ├── flight_search.py      # LangChain @tool for flight search
│   │       └── retry.py              # Async retry decorator with backoff
│   ├── tests/
│   │   ├── conftest.py               # Shared fixtures (mock_flight_client, mock_llm_provider)
│   │   ├── fixtures/                 # Test data fixtures
│   │   ├── unit/
│   │   │   ├── test_exceptions.py
│   │   │   ├── test_flight_models.py
│   │   │   ├── test_mock_client.py
│   │   │   └── test_retry.py
│   │   ├── integration/
│   │   │   ├── test_chat.py          # Chat endpoint integration tests
│   │   │   └── test_health.py
│   │   └── e2e/
│   │       ├── test_e2e.py           # Full flow with real LLM calls
│   │       └── test_e2e_manual.py
│   ├── pyproject.toml                # uv/pip config, pytest, mypy, ruff settings
│   └── uv.lock
├── frontend/
│   ├── src/
│   │   ├── main.tsx                  # React entry point
│   │   ├── App.tsx                   # Root component (renders ChatInterface)
│   │   ├── App.css
│   │   ├── index.css
│   │   ├── assets/
│   │   └── components/
│   │       ├── ChatInterface.tsx      # Main chat UI
│   │       ├── ProviderSelector.tsx   # LLM provider/model picker
│   │       ├── ThinkingCard.tsx       # Reasoning display
│   │       ├── ToolCallCard.tsx       # Tool call visualization
│   │       ├── ToolExecutionCard.tsx  # Tool execution status
│   │       └── ToolResultCard.tsx     # Tool result display
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig*.json
└── phases/                           # Phase documentation (empty)
```

## Key Locations

| What | Where |
|------|-------|
| API entry point | `backend/app/api/main.py` |
| API routes | `backend/app/api/routes/routes.py` |
| Chat logic | `backend/app/chat.py` |
| Config / env | `backend/app/config.py` |
| Domain models | `backend/app/models.py` |
| Tool implementations | `backend/app/tools/` |
| Backend tests | `backend/tests/` |
| Frontend entry | `frontend/src/main.tsx` |
| Chat UI | `frontend/src/components/ChatInterface.tsx` |
| Provider picker | `frontend/src/components/ProviderSelector.tsx` |

## Naming Conventions

### Backend (Python)
- Modules: `snake_case.py`
- Classes: `PascalCase` (`ChatService`, `FlightAPIClient`)
- Functions: `snake_case` (`search_flights`, `create_session`)
- Test files: `test_<module>.py`
- Fixtures: `snake_case` in `conftest.py`

### Frontend (TypeScript/React)
- Components: `PascalCase.tsx` (`ChatInterface.tsx`, `ToolCallCard.tsx`)
- Entry files: `camelCase` (`main.tsx`)
- No hooks directory yet
- No utility modules yet

## Where to Add New Code

| Type | Location |
|------|----------|
| New API route | `backend/app/api/routes/` |
| New tool | `backend/app/tools/` + register in `chat.py` |
| New Pydantic model | `backend/app/models.py` |
| New UI component | `frontend/src/components/` |
| New custom hook | `frontend/src/hooks/` (create dir) |
| Backend unit test | `backend/tests/unit/test_<module>.py` |
| Backend integration test | `backend/tests/integration/test_<feature>.py` |
| Backend e2e test | `backend/tests/e2e/test_<flow>.py` |
