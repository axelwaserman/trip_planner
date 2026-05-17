# Concerns

> Mapped: 2026-04-27

## Security

### CRITICAL: Fake Auth Implementation

`backend/app/api/routes/auth.py` contains a completely insecure auth system:
- Hardcoded user database (`fake_users_db`) with plaintext-prefixed passwords
- `fake_hash_password()` just prepends "fakehashed" to password
- `fake_decode_token()` treats the access token as the username directly
- Token endpoint returns username as access token
- Comment in code: "This doesn't provide any security at all"

**Risk**: If exposed to any network, auth provides zero protection.

### API Keys in Config

`backend/app/config.py` loads API keys from env vars (`openai_api_key`, `anthropic_api_key`). Config loaded as module-level singleton `settings = Settings()`. No validation that keys are present when provider is selected.

### No CORS Lockdown

CORS likely configured in `backend/app/api/main.py` but needs audit for production origins.

### No Rate Limiting

No rate limiting on any endpoint. Chat endpoint with LLM calls could be expensive if abused.

## Technical Debt

### In-Memory State

`backend/app/chat.py` stores all state in dicts:
- `_histories: dict[str, InMemoryChatMessageHistory]`
- `_metadata: dict[str, dict]`
- `_last_activity: dict[str, float]`

Server restart loses all sessions. No persistence layer.

### Tool Injection Pattern

`backend/app/chat.py:31` mutates module-level state:
```python
search_flights._flight_client = flight_client
```
Setting private attribute on a tool function at runtime. Fragile, not testable in isolation, breaks if multiple ChatService instances use different clients.

### Skipped Test Files

`backend/tests/integration/test_chat_service_mocked_llm.py.skip` and `.skip.bak` indicate abandoned test approach. Dead files.

### Inconsistent Status Codes

`test_chat.py` expects 201 for session creation, `test_e2e.py` expects 200. One must be wrong.

### Empty Phases Directory

`phases/` directory exists but is empty. Unclear purpose.

### No Frontend Architecture

Frontend is minimal:
- Single `App.tsx` rendering `ChatInterface`
- No routing
- No state management
- No error boundaries
- No API client abstraction
- No TypeScript strict mode verification needed (simple component tree)

## Performance

### No Session Cleanup Automation

`ChatService.cleanup_expired_sessions()` exists but nothing calls it automatically. Memory leak over time as sessions accumulate.

### No Streaming Backpressure

`chat_stream()` yields events without backpressure control. Slow clients could cause issues.

### Mock Client in Production Code

`MockFlightAPIClient` lives alongside `FlightAPIClient` in `backend/app/tools/flight_client.py`. Production code includes test utilities.

## Missing Infrastructure

- No database
- No CI/CD pipeline
- No Docker/containerization
- No logging configuration (beyond defaults)
- No health check beyond basic endpoint
- No OpenAPI documentation customization
- No frontend tests
- No environment-specific configs (dev/staging/prod)

## Outdated Model References

`backend/app/config.py` references `claude-3-5-sonnet-20241022` and `claude-3-5-haiku-20241022`. These are older model IDs. Current Claude models are 4.x family.

## Dependencies to Watch

- `langchain>=0.3.0` / `langgraph>=1.0.2` - fast-moving libraries, breaking changes common
- `pyjwt` and `pwdlib` in deps but auth is fake — unused or partially integrated
