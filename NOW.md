# Current Task: Session Management & Multi-Tab Support

**Status**: 🔄 IN PROGRESS  
**Priority**: P0 (Must Fix)  
**Estimated**: 3-4 hours  
**Phase**: Pre-Phase 4 Refactor

## Goal
Remove global `_global_chat_store` anti-pattern and enable independent sessions per browser tab.

## Subtasks
- [ ] Create `ChatSession` domain model with metadata in `app/domain/session.py`
  - Fields: session_id, created_at, last_active, metadata (dict for provider choice)
  - Methods: add_message(), get_messages(), update_metadata()
- [ ] Implement `SessionStore` ABC with `InMemorySessionStore` in `app/infrastructure/storage/session.py`
  - Methods: create_session(), get_session(), delete_session(), cleanup_expired()
- [ ] Add session lifecycle API in `app/api/routes/chat.py`
  - `POST /api/chat/session` - Create new session, return session_id
  - `GET /api/chat/session/{session_id}` - Get session info
- [ ] Refactor `ChatService` to accept session_id instead of using global store
  - Remove `_global_chat_store` from `app/chat.py`
  - Inject `SessionStore` via constructor
- [ ] Update frontend `ChatInterface.tsx` to initialize session on mount
  - Call `POST /api/chat/session` when component loads
  - Store session_id in component state
  - Send session_id with all chat requests

## Context
- **Pattern**: [Data Model Pattern](ARCHITECTURE.md#data-model-pattern) for ChatSession
- **Pattern**: [Abstract Client Pattern](ARCHITECTURE.md#abstract-client-pattern) for SessionStore ABC
- **Pattern**: [Dependency Injection Pattern](ARCHITECTURE.md#dependency-injection-pattern) for SessionStore

## Success Criteria
- ✅ Each browser tab creates independent session
- ✅ Global `_global_chat_store` removed from codebase
- ✅ All 122 tests still passing
- ✅ `just typecheck` passes

## Blockers
None

## Next Task
**Task 2: LLM Provider Abstraction Layer** (4-5h)
- Create `LLMProvider` Protocol with provider selection
- Refactor `ChatService` to accept injected provider
