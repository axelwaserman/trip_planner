# Phase 4.1: LLM Provider UI & Configuration

**Status**: 🔄 IN PROGRESS  
**Started**: 2025-11-14  
**Estimated**: 4-6 hours  
**Priority**: High

---

## Goal

Enable users to select their preferred LLM provider (Ollama, OpenAI, Anthropic) from the UI, with provider-specific model selection and API key configuration.

---

## Tasks

### Backend (2-3h)

- [ ] Update `config.py` to support multiple providers
  - Add optional API keys for OpenAI, Anthropic
  - Keep Ollama as default with no key required
  - Add provider-specific model lists

- [ ] Create `/api/providers` endpoint
  - Returns list of available providers
  - Returns available models per provider
  - Indicates which providers have valid credentials

- [ ] Update `ChatService` to accept provider/model in session metadata
  - Store provider choice in session when created
  - Initialize correct LLM based on session metadata
  - Fallback to config default if not specified

- [ ] Update session creation endpoint
  - Accept optional `provider` and `model` parameters
  - Validate provider/model combination
  - Store in session metadata

### Frontend (2-3h)

- [ ] Create `ProviderSelector` component
  - Dropdown for provider selection (Ollama/OpenAI/Anthropic)
  - Model dropdown that updates based on selected provider
  - Show API key status indicator
  - Persist selection to localStorage

- [ ] Update `ChatInterface` to use provider selection
  - Pass provider/model to session creation
  - Display current provider in UI
  - Allow changing provider (creates new session)

- [ ] Add settings panel/modal
  - Configure API keys (stored in localStorage, never sent to backend)
  - Test provider connection
  - Clear stored credentials

---

## Implementation Plan

### Step 1: Backend Configuration (30min)
1. Update `Settings` in `config.py` with provider fields
2. Add provider validation logic
3. Add model lists per provider

### Step 2: Provider API Endpoint (45min)
1. Create `/api/providers` route
2. Return available providers with model lists
3. Add credential validation (check if API keys work)

### Step 3: Session Metadata (1h)
1. Update `ChatService` constructor to accept provider config
2. Modify `create_session()` to accept provider/model params
3. Store metadata in session
4. Use metadata when initializing LLM in `chat_stream()`

### Step 4: Frontend Provider Selector (1.5h)
1. Create `ProviderSelector` component with dropdowns
2. Fetch providers from API on mount
3. Handle provider/model state
4. Persist to localStorage

### Step 5: Integration (1h)
1. Add provider selector to ChatInterface header
2. Pass provider/model to session creation
3. Display current provider
4. Test with different providers

### Step 6: Settings Panel (1h - Optional for v1)
1. Modal for API key configuration
2. Store securely in localStorage
3. Test connection button
4. Clear credentials option

---

## Success Criteria

- ✅ Users can select provider from UI
- ✅ Users can select model for chosen provider
- ✅ Session uses selected provider/model
- ✅ Config supports multiple API keys
- ✅ Provider selection persists across page reloads
- ✅ All existing tests still pass
- ✅ Works with all three providers (Ollama, OpenAI, Anthropic)

---

## Technical Notes

**Provider Initialization Pattern**:
```python
# Use init_chat_model with provider selection
llm = init_chat_model(
    model=session_metadata.get("model", settings.ollama_model),
    model_provider=session_metadata.get("provider", "ollama"),
    base_url=settings.ollama_base_url if provider == "ollama" else None,
    api_key=get_api_key(provider),  # From settings
    reasoning=True,
)
```

**Session Metadata Structure**:
```json
{
  "provider": "ollama",
  "model": "qwen3:4b",
  "created_at": "2025-11-14T10:30:00Z"
}
```

**Frontend State**:
- Use `useState` for provider/model selection
- Store in localStorage as `{ provider, model }`
- Fetch on mount, fallback to defaults

---

## Next Phase

After Phase 4.1 completion:
- **Phase 4.2**: Structured Tool Output (2-3h)
