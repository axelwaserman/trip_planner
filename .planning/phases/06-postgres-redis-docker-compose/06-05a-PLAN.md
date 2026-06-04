---
phase: 06-postgres-redis-docker-compose
plan: 05a
type: execute
wave: 5
depends_on:
  - 06-04
files_modified:
  - backend/app/chat/models.py
  - backend/app/chat/service.py
  - backend/app/chat/repository.py
  - backend/app/chat/store.py
  - backend/app/chat/__init__.py
  - backend/app/api/routes/routes.py
  - backend/app/providers/models.py
  - backend/app/llm/factory.py
  - backend/app/llm/base.py
  - backend/tests/unit/chat/test_stream_event_wire_compat.py
  - backend/tests/unit/chat/test_conversation_create_request_split.py
  - backend/tests/unit/test_provider_info_split.py
  - backend/tests/unit/tools/test_flight_search_no_backdoor.py
  - backend/tests/integration/test_conversation_routes.py
  - backend/tests/integration/test_providers_endpoint.py
  - .planning/phases/06-postgres-redis-docker-compose/06-05a-SUMMARY.md
autonomous: true
requirements:
  - REQ-p5-conversation-rename
  - REQ-p5-session-create-request-split
  - REQ-p5-provider-info-split
  - REQ-p5-flight-client-di
tags:
  - rename
  - pydantic-srp-split
  - wire-format
  - phase-5-carryforward
  - backend-only

must_haves:
  truths:
    - "Backend production code references zero `session_id` / `SessionId` / `/api/chat/sessions` / `/api/chat/session` tokens (auth-side `session` references for JWT/login lifetime are exempt per D-03)"
    - "`/api/chat/conversations` (GET list, GET detail), `POST /api/chat/conversation`, and `DELETE /api/chat/conversation/{conversation_id}` are the only chat-conversation routes; the legacy `/api/chat/sessions*` paths return 404"
    - "SSE event JSON serialises with `conversation_id` LAST on every subclass of `StreamEvent`; the wire-compat golden test under `tests/unit/chat/test_stream_event_wire_compat.py` is regenerated and passes"
    - "`POST /api/chat/conversation` accepts `{target: {provider, model}, credentials: {base_url, api_key}}` and rejects the legacy flat shape with HTTP 422"
    - "`ProviderCredentials.base_url` and `ProviderCredentials.api_key` field validators are byte-equivalent to the deleted `SessionCreateRequest` validators (relocated, not rewritten)"
    - "`GET /api/providers` returns `LocalProviderInfo` for ollama/lmstudio (with `base_url: str`) and `CloudProviderInfo` for openai/anthropic (with `api_key_configured: bool`); the response shape is governed by a `ProviderInfoResponse` discriminated alias distinct from any internal `ProviderInfo`"
    - "REQ-p5-flight-client-di is closed: `rg --no-filename '_flight_client' backend/app` matches only the legitimate `ChatService.__init__` constructor parameter assignment (`self._flight_client = flight_client`) and the agent build-time forward of that attribute (`flight_client=self._flight_client`); no `search_flights._flight_client = ...` assignment, no `getattr(search_flights, '_flight_client', ...)` peek"
  artifacts:
    - path: "backend/app/chat/models.py"
      provides: "ConversationTarget + ProviderCredentials + ConversationCreateRequest; SessionCreateRequest deleted; SSE events use conversation_id LAST"
      contains: "class ConversationTarget, class ProviderCredentials, class ConversationCreateRequest, class ChatConversationInfo"
    - path: "backend/app/providers/models.py"
      provides: "LocalProviderInfo + CloudProviderInfo + ProviderInfoResponse discriminated union; legacy ProviderInfo deleted"
      contains: "class LocalProviderInfo, class CloudProviderInfo, ProviderInfoResponse"
    - path: "backend/app/api/routes/routes.py"
      provides: "Conversation-renamed routes consuming ConversationCreateRequest and emitting ProviderInfoResponse"
      exports: ["create_conversation", "delete_conversation", "list_conversations", "get_chat_conversation_history", "chat", "retry_tool_call", "get_providers"]
    - path: "backend/tests/unit/chat/test_stream_event_wire_compat.py"
      provides: "Wire-format golden file regenerated with conversation_id LAST"
    - path: "backend/tests/integration/test_conversation_routes.py"
      provides: "End-to-end coverage for the new conversation routes plus legacy 404 lock"
    - path: "backend/tests/unit/chat/test_conversation_create_request_split.py"
      provides: "REQ-p5-session-create-request-split unit coverage (SRP boundary + relocated validators)"
    - path: "backend/tests/unit/test_provider_info_split.py"
      provides: "REQ-p5-provider-info-split unit coverage (Local/Cloud discriminator + api_key_configured masking)"
    - path: "backend/tests/unit/tools/test_flight_search_no_backdoor.py"
      provides: "REQ-p5-flight-client-di lock — confirms no _flight_client back-door reappears"
  key_links:
    - from: "backend/app/api/routes/routes.py::create_conversation"
      to: "backend/app/chat/models.py::ConversationCreateRequest"
      via: "request: ConversationCreateRequest body"
      pattern: "request: ConversationCreateRequest"
    - from: "backend/app/api/routes/routes.py::get_providers"
      to: "backend/app/providers/models.py::ProviderInfoResponse"
      via: "-> dict[str, ProviderInfoResponse]"
      pattern: "dict\\[str, ProviderInfoResponse\\]"
---

<objective>
Backend slice of the Phase 5 carry-forward refactor: rename `session` → `conversation` codebase-wide on the backend (D-03), split `SessionCreateRequest` into `ConversationTarget` + `ProviderCredentials` + `ConversationCreateRequest` (REQ-p5-session-create-request-split), split `ProviderInfo` into `LocalProviderInfo` + `CloudProviderInfo` behind a `ProviderInfoResponse` discriminated union (REQ-p5-provider-info-split), and lock `REQ-p5-flight-client-di` as already-closed by Phase 5 with a Phase 6 regression test.

Purpose: This plan owns the wire-format ownership: DTO classes, SSE event field declarations, route paths, and Pydantic validators all live on the backend. Plan 06-05b ships the frontend follow-on (TypeScript types, hook/component renames, provider response decoder) and depends_on this plan completing first to keep the atomic-PR semantics from RESEARCH OQ-5 — but the wave structure executes them sequentially within Wave 5 so `master` stays green at the squash boundary.
Output: rename-complete backend, two DTO splits with dedicated unit tests, regenerated SSE wire-format golden, integration test asserting legacy `/api/chat/sessions*` paths return 404 while new `/api/chat/conversations*` routes work, and a regression-locking flight-client unit test.
</objective>

<execution_context>
@/Users/axel/code/trip_planner/.claude/get-shit-done/workflows/execute-plan.md
@/Users/axel/code/trip_planner/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/06-postgres-redis-docker-compose/06-CONTEXT.md
@.planning/phases/06-postgres-redis-docker-compose/06-RESEARCH.md
@.planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md
@.planning/phases/06-postgres-redis-docker-compose/06-VALIDATION.md
@.planning/phases/06-postgres-redis-docker-compose/06-04-SUMMARY.md
@.planning/phases/05-pydanticai-migration/05-VERIFICATION.md
@CLAUDE.md
@backend/app/chat/models.py
@backend/app/chat/service.py
@backend/app/api/routes/routes.py
@backend/app/providers/models.py
@backend/app/tools/flight_search.py
@backend/app/chat/deps.py
@backend/tests/unit/chat/test_stream_event_wire_compat.py

<interfaces>
<!-- StreamEvent SSE wire layout (Phase 4.7 lock — `session_id` LAST per subclass): -->
- `ContentEvent`: `type: Literal["content"], chunk: str = "", session_id: str` → rename to `conversation_id: str`
- `ThinkingEvent`: `type: Literal["thinking"], chunk: str, session_id: str` → rename
- `ToolCallEvent`: `type: Literal["tool_call"], tool_name: str, tool_args: dict[str, Any], session_id: str` → rename
- `ToolResultEvent`: `type: Literal["tool_result"], tool_name: str, tool_result: str, elapsed_ms: int, session_id: str` → rename
- `ErrorEvent`: keeps `session_id` LAST (line 171 of `chat/models.py`); rename to `conversation_id: str`. Wire-format guard in `tests/unit/chat/test_stream_event_wire_compat.py` regenerates the four happy-path goldens.

<!-- Phase 5 / Phase 4.7 wire-format invariant (Phase 4.7 OQ-01 lock): -->
- `conversation_id` MUST stay declared on each subclass (NOT hoisted into the StreamEvent ABC) so Pydantic's per-subclass field-order serialisation continues to emit the field LAST. Hoisting was empirically verified to break the wire format in Phase 4.7.

<!-- Routes — paths and bodies (Phase 6 D-03 rename + REQ-p5-session-create-request-split + REQ-p5-provider-info-split): -->
- `POST /api/chat/conversation`               body: `ConversationCreateRequest`        response: `{conversation_id, provider, model}` (existing fields, key renamed)
- `DELETE /api/chat/conversation/{conversation_id}`   path param renamed
- `GET /api/chat/conversations`                response: `ChatConversationsListResponse` (renamed from `ChatSessionsListResponse`)
- `GET /api/chat/conversations/{conversation_id}`     response: `ChatConversationHistoryResponse` (renamed from `ChatSessionHistoryResponse`)
- `POST /api/chat`                              body: `ChatRequest` (carries `conversation_id`)
- `POST /api/chat/retry`                       body: `RetryRequest` (carries `conversation_id`)
- `GET /api/providers`                          response: `dict[str, ProviderInfoResponse]` (discriminated by `type`)

<!-- Pydantic SRP split target (CONTEXT/RESEARCH §Pattern 5; PATTERNS.md §Provider-info wire format split): -->
class ConversationTarget(BaseModel):
    provider: str | None = Field(default=None, description="LLM provider (ollama, openai, anthropic)")
    model: str | None = Field(default=None, description="Model name for the provider")

class ProviderCredentials(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    # _strip_and_bound_api_key + _validate_base_url validators relocated VERBATIM from SessionCreateRequest

class ConversationCreateRequest(BaseModel):
    target: ConversationTarget = Field(default_factory=ConversationTarget)
    credentials: ProviderCredentials | None = None

<!-- Provider response discriminated union (RESEARCH §Provider-info split + PATTERNS.md §Provider-info wire format split): -->
class LocalProviderInfo(BaseModel):
    type: Literal["local"] = "local"
    available: bool
    models: list[str] = Field(default_factory=list)
    base_url: str  # always present for local providers

class CloudProviderInfo(BaseModel):
    type: Literal["cloud"] = "cloud"
    available: bool
    models: list[str] = Field(default_factory=list)
    api_key_configured: bool  # boolean only — never the api_key itself

ProviderInfoResponse = Annotated[LocalProviderInfo | CloudProviderInfo, Field(discriminator="type")]

<!-- Reserved word — D-03 explicit exclusion (DO NOT RENAME): -->
- Auth-side `session` references survive: JWT/cookie/login lifetime tokens. The rename's grep gates use `grep -v 'auth/' | grep -v 'JWT\|jwt\|expir'` to exclude these from the zero-match audit.
- `cleanup_expired_sessions` ChatService method name MAY be renamed to `cleanup_expired_conversations` for internal consistency (planner discretion); the public surface is unaffected.

<!-- REQ-p5-flight-client-di status (Phase 5 verification truth #5; RESEARCH §Architectural Responsibility Map A7): -->
- `backend/app/chat/deps.py` declares `make_chat_run_context` and explicitly closes the back-door per Phase 5 D-06.
- `backend/app/tools/flight_search.py` reads from `ctx.deps.flight_client` (RunContext-based), NOT a module attribute.
- Surviving legitimate references in `backend/app/chat/service.py`:
    - line 108: `self._flight_client = flight_client` (constructor parameter; PostgresChatService DI surface)
    - line 321: `flight_client=self._flight_client` (forwards into `ChatRunDeps`)
  These are the contract this plan locks; the prohibited form is `search_flights._flight_client = X` (module-attribute assignment) and `getattr(search_flights, "_flight_client", None)` (back-door read).

<!-- Phase 5 plan 04 also added `tests/unit/tools/test_flight_search_no_backdoor.py`. This plan ADDS forensic assertions or extends; if the file already exists from Phase 5, this plan extends it with a `grep`-style regression assertion. -->
</interfaces>
</context>

### Cross-plan coordination

- **06-05a → 06-05b atomic-PR semantics:** This plan ships the backend wire-format break. Plan 06-05b ships the frontend types/hooks/components rename in the SAME wave. RESEARCH OQ-5 ("one atomic PR") is preserved by execute-phase landing both as a single squash-merge — `master` between the 06-05a and 06-05b commits is broken-by-design (frontend will fail to compile against renamed backend types). The wave-5 dependency `06-05b: depends_on: [06-04, 06-05a]` enforces sequencing.
- This plan does NOT modify any frontend files. The `frontend/src/types/chat.ts` interface contract for SSE events is the public surface that 06-05b will mirror.

<tasks>

<task type="auto">
  <name>Task 1: Backend rename — `session` → `conversation` across DTOs, services, routes, and SSE wire format</name>
  <files>backend/app/chat/models.py, backend/app/chat/service.py, backend/app/chat/repository.py, backend/app/chat/store.py, backend/app/chat/__init__.py, backend/app/api/routes/routes.py, backend/app/llm/factory.py, backend/app/llm/base.py, backend/tests/unit/chat/test_stream_event_wire_compat.py</files>
  <read_first>
    - backend/app/chat/models.py (full file — focus on lines 119-171 StreamEvent subclasses, lines 179-231 SessionCreateRequest, lines 239-271 ChatRequest/RetryRequest/ChatSessionInfo)
    - backend/app/chat/service.py (full file — every `session_id`, `_metadata`, `_first_message_preview`, `cleanup_expired_sessions`, `delete_session`, `chat_stream`)
    - backend/app/api/routes/routes.py (full file — all `/api/chat/session*` routes, `request.session_id`, `chat_service._metadata`, `_LOCAL_PROVIDER_NAMES` location; also the placeholder deps `get_message_store` + `get_conversation_repo` that Plan 06-04 added)
    - backend/app/chat/repository.py (Plan 03 — ConversationRecord; ensure ChatConversationInfo mapping in service.py uses ConversationRecord)
    - backend/app/chat/store.py (Plan 03/04 — ConversationConcurrentAppendError; MessageStore signatures already use UUID conversation_id, confirm)
    - backend/app/chat/__init__.py (re-exports)
    - backend/tests/unit/chat/test_stream_event_wire_compat.py (Phase 4.7 wire-format guard — golden JSON strings hard-coded with `session_id`)
    - backend/app/llm/factory.py (any `session_id`/`SessionLLMConfig` references — check `SessionLLMConfig` is renamed or stays as-is per D-03 reserved-word boundary; the request DTO `SessionLLMConfig` is the *internal* shape passed to the LLM factory and may stay if it's not on the wire — planner decides)
    - backend/app/llm/base.py (any session-named tokens)
    - .planning/phases/06-postgres-redis-docker-compose/06-CONTEXT.md (D-03 reserved-word boundary — auth/JWT-session is preserved)
    - .planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md (§`backend/app/api/routes/routes.py` rename + request-model split; §Ownership 404-shape preserved)
    - CLAUDE.md (StrEnum convention; immutable patterns; ABC over Protocol; ruff line length 120)
  </read_first>
  <action>
    Apply a mechanical rename across `backend/app/` (excluding `backend/app/auth/` and any token containing `JWT`/`jwt`/`expir` per D-03 reserved-word boundary):
      - identifiers: `session_id` → `conversation_id`; `SessionId` → `ConversationId` (if any); `_first_message_preview(session_id=...)` keyword arg adjustments; `chat_service._metadata` keys logically rename `session_id` lookups but the Python attribute name `_metadata` itself stays.
      - HTTP paths: `/api/chat/session` → `/api/chat/conversation`; `/api/chat/session/{session_id}` → `/api/chat/conversation/{conversation_id}`; `/api/chat/sessions` → `/api/chat/conversations`; `/api/chat/sessions/{session_id}` → `/api/chat/conversations/{conversation_id}`.
      - Pydantic class renames: `ChatSessionInfo` → `ChatConversationInfo`; `ChatSessionsListResponse` → `ChatConversationsListResponse`; `ChatSessionHistoryResponse` → `ChatConversationHistoryResponse`; `ChatSessionMessage` → `ChatConversationMessage` (only if it exists). The internal `SessionLLMConfig` (factory-layer DTO that does NOT cross the wire) stays — D-03 reserves `session` for runtime-lifetime concepts and `SessionLLMConfig` is the runtime LLM-binding shape; document this exemption in a one-line comment on the class.
      - Field renames inside DTOs: `session_id: str` → `conversation_id: str` on `ChatRequest`, `RetryRequest`, `ChatConversationInfo`, `ChatConversationHistoryResponse`, `ErrorEvent`, `ContentEvent`, `ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`. Each rename preserves field declaration ORDER (the field stays LAST in the StreamEvent subclasses per the Phase 4.7 OQ-01 lock).
      - Method renames inside `ChatService`: `cleanup_expired_sessions` → `cleanup_expired_conversations`; `delete_session` → `delete_conversation`; `list_sessions_for_user` → `list_conversations_for_user`; `get_history_for_user(session_id, ...)` → `get_history_for_user(conversation_id, ...)`. Update the lifespan call site in `app/api/main.py` (Plan 04 set up the rewire — adjust the method name there).
      - Route handler renames: `create_session` → `create_conversation`; `delete_session` → `delete_conversation`; `list_sessions` → `list_conversations`; `get_chat_session_history` → `get_chat_conversation_history`. The `chat` and `retry_tool_call` route handlers keep their names (they take `conversation_id` via the request body, not the route path).
      - Logging messages — string literals containing `session %s` adjust to `conversation %s` in `logger.exception(...)` and `logger.info(...)` calls.
    The Pydantic v2 alias-tolerant rename rule: do NOT add `validation_alias`/`serialization_alias` shims for the old `session_id` JSON key — the wire format is breaking by design (frontend rides in 06-05b).
    Regenerate `tests/unit/chat/test_stream_event_wire_compat.py` golden assertions: replace every `"session_id":"s1"` JSON literal with `"conversation_id":"s1"` and update the keyword arg in event constructors. Preserve the field-order assertion (the wire layout still puts the conversation key LAST). Keep the existing test names; do not delete tests.
    Final hygiene gate: run `rg -n --no-filename 'session_id|SessionId|/api/chat/sessions|/api/chat/session\b' backend/app | grep -v 'auth/' | grep -v 'JWT\|jwt\|expir' | grep -v 'SessionLLMConfig\|SessionCreateError'` and assert zero matches before committing.
  </action>
  <verify>
    <automated>cd backend &amp;&amp; uv run pytest tests/unit/chat/test_stream_event_wire_compat.py -x --tb=short &amp;&amp; uv run mypy app/chat/ app/api/routes/ app/llm/ &amp;&amp; uv run ruff check app/ &amp;&amp; rg -n --no-filename 'session_id|SessionId|/api/chat/sessions|/api/chat/session\b' app | grep -v 'auth/' | grep -v 'JWT\|jwt\|expir' | grep -v 'SessionLLMConfig\|SessionCreateError' | grep -v '^#' | wc -l | tr -d ' ' | grep -qx 0</automated>
  </verify>
  <acceptance_criteria>
    - `rg --no-filename 'session_id|SessionId' backend/app | grep -v 'auth/' | grep -v 'JWT\|jwt\|expir' | grep -v 'SessionLLMConfig\|SessionCreateError' | grep -v '^\s*#'` returns zero non-comment matches.
    - `rg '/api/chat/sessions|/api/chat/session\b' backend/app | grep -v '^\s*#'` returns zero matches.
    - The four route handlers (`create_conversation`, `delete_conversation`, `list_conversations`, `get_chat_conversation_history`) exist and decorate `/api/chat/conversation`/`/api/chat/conversations*` paths.
    - `tests/unit/chat/test_stream_event_wire_compat.py` passes; the golden JSON strings include `"conversation_id":"s1"` (LAST in the JSON shape — assert via the existing test body).
    - `mypy --strict app/chat/ app/api/routes/ app/llm/` passes.
    - `ruff check app/` passes.
    - The five SSE event subclasses (`ContentEvent`, `ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`, `ErrorEvent`) keep `conversation_id` declared LAST per subclass (Phase 4.7 OQ-01 lock — assert via `model_fields` order on each class).
  </acceptance_criteria>
  <done>Backend production code has zero non-auth `session_id` references; SSE wire format emits `conversation_id` LAST; all renamed routes resolve through the rewired ChatService.</done>
</task>

<task type="auto">
  <name>Task 2: Split SessionCreateRequest into ConversationTarget + ProviderCredentials + ConversationCreateRequest (REQ-p5-session-create-request-split)</name>
  <files>backend/app/chat/models.py, backend/app/api/routes/routes.py, backend/tests/unit/chat/test_conversation_create_request_split.py</files>
  <read_first>
    - backend/app/chat/models.py after Task 1 (find `SessionCreateRequest` lines 179-231 — the four fields and two validators are the donor source)
    - backend/app/api/routes/routes.py after Task 1 (`create_conversation` handler that consumes `SessionCreateRequest`; lines around 290-370 show the chat_service.create_conversation call site)
    - backend/app/llm/factory.py (`SessionLLMConfig` — the *internal* DTO that the route constructs from the request body; `provider`, `model`, `base_url`, `api_key` fields)
    - .planning/phases/06-postgres-redis-docker-compose/06-RESEARCH.md (§Pattern 5 — Pydantic v2 SRP-Split Request Model; relocate validators VERBATIM)
    - .planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md (§`backend/app/api/routes/routes.py` — Phase 6 request-split block; §Pydantic Data Model Pattern)
    - CLAUDE.md (Pydantic Data Model Pattern; modern type syntax `str | None`)
  </read_first>
  <action>
    In `backend/app/chat/models.py`, declare three new Pydantic v2 BaseModel classes ABOVE the existing `ChatRequest` (so they're available to the route handler signature):
      - `class ConversationTarget(BaseModel)`: docstring "What to talk to (Pydantic SRP split — REQ-p5-session-create-request-split)"; fields `provider: str | None = Field(default=None, description="LLM provider (ollama, openai, anthropic)")` and `model: str | None = Field(default=None, description="Model name for the provider")`. NO validators.
      - `class ProviderCredentials(BaseModel)`: docstring "How to reach a provider — relocated `SessionCreateRequest` validators (REQ-p5-session-create-request-split)"; fields `base_url: str | None = None` and `api_key: str | None = None`. RELOCATE the two validators from `SessionCreateRequest` byte-equivalent — `_strip_and_bound_api_key` (the 256-char + strip + None-on-empty body, lines 207-218 of pre-Task-1 chat/models.py) and `_validate_base_url` (the SSRF allowlist body, lines 220-231). Do NOT rewrite the bodies — copy exactly so the existing security tests transfer.
      - `class ConversationCreateRequest(BaseModel)`: docstring "Request body for `POST /api/chat/conversation` (Phase 6 — REQ-p5-session-create-request-split)."; fields `target: ConversationTarget = Field(default_factory=ConversationTarget)` and `credentials: ProviderCredentials | None = None`. NO validators (delegated to ProviderCredentials).
    DELETE the legacy `SessionCreateRequest` class (now superseded). Confirm nothing else in `backend/app/` references it via `rg 'SessionCreateRequest' backend/app/`.
    Update `backend/app/api/routes/routes.py::create_conversation` (post-Task-1 name):
      - signature accepts `request: ConversationCreateRequest | None = None` (default kept so the caller can omit credentials and the empty target falls back to defaults — preserves the existing behaviour).
      - body construction: `target = request.target if request else ConversationTarget()`; `credentials = request.credentials if request else None`; build the existing `SessionLLMConfig` (the internal shape used by `chat_service.create_conversation(...)`) from `target.provider`, `target.model`, `credentials.base_url if credentials else None`, `credentials.api_key if credentials else None`. The internal `SessionLLMConfig` shape does NOT change (preserves the LLM-factory contract).
      - response payload: `{"conversation_id": ..., "provider": ..., "model": ...}` (already renamed in Task 1).
    Create `backend/tests/unit/chat/test_conversation_create_request_split.py` (AAA pattern, async-only where needed):
      - `test_conversation_target_accepts_minimal_payload`: `ConversationTarget()` with no fields validates to None defaults.
      - `test_provider_credentials_strips_and_bounds_api_key`: `ProviderCredentials(api_key="  abc  ")` normalises to `"abc"`; oversize (>256 chars) raises ValidationError; empty-after-strip becomes None.
      - `test_provider_credentials_ssrf_allowlist`: assert `ProviderCredentials(base_url="http://localhost:11434")` validates; `ProviderCredentials(base_url="http://example.com")` raises ValidationError ("base_url host must be localhost..."); `ftp://` raises ("must be http or https").
      - `test_conversation_create_request_nests_target_and_credentials`: `ConversationCreateRequest(target={"provider":"ollama","model":"qwen3"}, credentials={"base_url":"http://localhost:11434","api_key":"sk-fake"})` validates; flat shape `{"provider":"ollama","model":"qwen3"}` is REJECTED at the API boundary by FastAPI's request-body parser (assert via TestClient `POST /api/chat/conversation` returns 422 — this part lives in Task 4's integration test; here we assert direct Pydantic validation on the model only).
    Path-based selection: file lives under `tests/unit/chat/`; do NOT add `@pytest.mark.unit`.
  </action>
  <verify>
    <automated>cd backend &amp;&amp; uv run pytest tests/unit/chat/test_conversation_create_request_split.py -x --tb=short &amp;&amp; uv run python -c "from app.chat.models import ConversationTarget, ProviderCredentials, ConversationCreateRequest; assert hasattr(ProviderCredentials, '_strip_and_bound_api_key') or '_strip_and_bound_api_key' in {v.func.__name__ for v in ProviderCredentials.__pydantic_decorators__.field_validators.values()}, 'validator did not relocate'; print('OK')" &amp;&amp; ! rg 'SessionCreateRequest' backend/app/</automated>
  </verify>
  <acceptance_criteria>
    - `ConversationTarget`, `ProviderCredentials`, `ConversationCreateRequest` exist in `app/chat/models.py`; `SessionCreateRequest` no longer exists.
    - The two validators (`_strip_and_bound_api_key`, `_validate_base_url`) live on `ProviderCredentials` with bodies byte-equivalent to the pre-split versions (verified by inspecting source — same allowlist set, same length cap).
    - `POST /api/chat/conversation` route handler accepts `ConversationCreateRequest`; the call site builds `SessionLLMConfig` from `target.provider`, `target.model`, `credentials.base_url`, `credentials.api_key`.
    - All four unit tests in `test_conversation_create_request_split.py` pass.
    - `rg 'SessionCreateRequest' backend/app/` returns zero matches.
  </acceptance_criteria>
  <done>Pydantic SRP split landed; SSRF + length validators relocated verbatim; ConversationCreateRequest is the route's body type.</done>
</task>

<task type="auto">
  <name>Task 3: Split ProviderInfo into LocalProviderInfo + CloudProviderInfo + ProviderInfoResponse (REQ-p5-provider-info-split)</name>
  <files>backend/app/providers/models.py, backend/app/api/routes/routes.py, backend/tests/unit/test_provider_info_split.py</files>
  <read_first>
    - backend/app/providers/models.py (full file — current `ProviderInfo` class at lines 31-47; `SessionCreateError` and `ProviderRefreshEntry`/`ProviderRefreshResponse` are out-of-scope for this REQ)
    - backend/app/api/routes/routes.py (`get_providers` handler — lines 428-488 build a `dict[str, ProviderInfo]` with ollama/lmstudio/openai/anthropic entries)
    - backend/app/config.py (`Settings.ollama_base_url`, `Settings.lmstudio_base_url`, `get_available_providers()` for cloud entries; `Settings.openai_api_key`, `Settings.anthropic_api_key` for `api_key_configured` derivation)
    - backend/app/chat/models.py (`StreamEvent` ABC + multi-inheritance subclass — pattern reference for discriminated unions; lines 68-171)
    - .planning/phases/06-postgres-redis-docker-compose/06-RESEARCH.md (§Pydantic v2 discriminated subclass pattern; mirrors `StreamEvent(ABC)` from Phase 5)
    - .planning/phases/06-postgres-redis-docker-compose/06-PATTERNS.md (§Provider-info wire format split — `Annotated[A | B, Field(discriminator="type")]`)
    - CLAUDE.md (Pydantic Data Model Pattern; never persist or log api_key — `api_key_configured: bool` is the wire shape)
  </read_first>
  <action>
    In `backend/app/providers/models.py`, REPLACE the existing `ProviderInfo` class with two siblings + a discriminated alias:
      - `from typing import Annotated, Literal` at the top of the file (reuse existing `Field` import).
      - `class LocalProviderInfo(BaseModel)`: docstring "Local-provider response shape (ollama, lmstudio) — base_url is always present."; `type: Literal["local"] = "local"`; `available: bool`; `models: list[str] = Field(default_factory=list)`; `base_url: str = Field(..., description="Local-provider base URL — must be present.")`. Field order documented as part of the wire contract; `type` LAST? Actually Phase 6 has no Phase 4.7-style wire-byte lock for providers — declare `type` FIRST (discriminator convention) and document this in the docstring.
      - `class CloudProviderInfo(BaseModel)`: docstring "Cloud-provider response shape (openai, anthropic) — `api_key_configured` boolean only; the api_key itself never crosses the wire (D-09 lock from Phase 5)."; `type: Literal["cloud"] = "cloud"`; `available: bool`; `models: list[str] = Field(default_factory=list)`; `api_key_configured: bool = Field(..., description="True iff Settings has a non-empty api_key for this provider.")`.
      - Module-level alias: `ProviderInfoResponse = Annotated[LocalProviderInfo | CloudProviderInfo, Field(discriminator="type")]`. Add a `# noqa: PYI...` comment if mypy complains; otherwise keep as-is.
      - DELETE the legacy `ProviderInfo` class.
    Update `backend/app/api/routes/routes.py::get_providers`:
      - import `LocalProviderInfo`, `CloudProviderInfo`, `ProviderInfoResponse` (replace the `ProviderInfo` import on line 27 of routes.py).
      - return-type annotation: `-> dict[str, ProviderInfoResponse]` (FastAPI accepts the Annotated alias).
      - replace `result["ollama"] = ProviderInfo(available=..., models=..., base_url=...)` with `result["ollama"] = LocalProviderInfo(available=bool(cache.get("ollama", [])), models=cache.get("ollama", []), base_url=settings.ollama_base_url)`. Same shape for `lmstudio` (with `settings.lmstudio_base_url`).
      - replace `result[name] = ProviderInfo(...)` for openai/anthropic with `result[name] = CloudProviderInfo(available=bool(entry["available"]), models=list(models_field) if isinstance(models_field, list) else [], api_key_configured=bool(getattr(settings, f"{name}_api_key", None)))`. The `api_key_configured` derivation reads the existing `Settings.openai_api_key`/`anthropic_api_key` fields — if the names differ in `app/config.py`, follow the convention there (planner discretion: prefer the existing Settings field; if Settings exposes a method like `has_api_key(name)`, use that).
    Frontend response decoder lives in Plan 06-05b — this plan ships the backend split alone.
    Create `backend/tests/unit/test_provider_info_split.py`:
      - `test_local_provider_info_validates_with_base_url`: `LocalProviderInfo(available=True, models=["qwen3"], base_url="http://localhost:11434")` round-trips via `model_dump_json()` containing `"type":"local"`.
      - `test_local_provider_info_requires_base_url`: omitting `base_url` raises ValidationError (the field is required).
      - `test_cloud_provider_info_carries_api_key_configured_boolean`: `CloudProviderInfo(available=True, models=["gpt-4"], api_key_configured=True)` round-trips; `api_key_configured` is the only credential signal — assert there is no `api_key` field on the class via `assert "api_key" not in CloudProviderInfo.model_fields`.
      - `test_provider_info_response_discriminates_by_type`: validate `{"type":"local","available":True,"models":[],"base_url":"http://x"}` resolves to `LocalProviderInfo`; validate `{"type":"cloud","available":True,"models":[],"api_key_configured":False}` resolves to `CloudProviderInfo`. Use `pydantic.TypeAdapter(ProviderInfoResponse).validate_python({...})`.
      - `test_provider_info_response_rejects_unknown_type`: `{"type":"weird","available":True,"models":[]}` raises ValidationError.
    Path-based selection: `tests/unit/test_provider_info_split.py`; no marker.
  </action>
  <verify>
    <automated>cd backend &amp;&amp; uv run pytest tests/unit/test_provider_info_split.py -x --tb=short &amp;&amp; uv run python -c "from app.providers.models import LocalProviderInfo, CloudProviderInfo, ProviderInfoResponse; from pydantic import TypeAdapter; ta = TypeAdapter(ProviderInfoResponse); local = ta.validate_python({'type':'local','available':True,'models':[],'base_url':'http://x'}); assert isinstance(local, LocalProviderInfo); cloud = ta.validate_python({'type':'cloud','available':True,'models':[],'api_key_configured':False}); assert isinstance(cloud, CloudProviderInfo); print('OK')" &amp;&amp; ! rg '^class ProviderInfo\(' backend/app/</automated>
  </verify>
  <acceptance_criteria>
    - `LocalProviderInfo`, `CloudProviderInfo`, and `ProviderInfoResponse` exported from `app.providers.models`; legacy `ProviderInfo` class deleted.
    - `LocalProviderInfo.base_url` is required (`Field(...)` without default); `CloudProviderInfo.api_key_configured` is `bool` and `api_key` is NOT a field on either class.
    - `GET /api/providers` route returns `dict[str, ProviderInfoResponse]`; `result["ollama"]` and `result["lmstudio"]` are `LocalProviderInfo`; `result["openai"]` and `result["anthropic"]` are `CloudProviderInfo`.
    - Five unit tests in `test_provider_info_split.py` pass.
    - `mypy --strict app/providers/ app/api/routes/` passes; `ruff check app/providers/ app/api/routes/` passes.
  </acceptance_criteria>
  <done>ProviderInfo split into discriminated Local/Cloud subclasses; route emits the discriminated response; api_key never crosses the wire.</done>
</task>

<task type="auto">
  <name>Task 4: Integration tests for renamed routes + 422-on-legacy-shape + flight-client-DI regression lock</name>
  <files>backend/tests/integration/test_conversation_routes.py, backend/tests/integration/test_providers_endpoint.py, backend/tests/unit/tools/test_flight_search_no_backdoor.py</files>
  <read_first>
    - backend/app/api/routes/routes.py after Tasks 1-3 (renamed handlers, ConversationCreateRequest body, ProviderInfoResponse return type)
    - backend/tests/integration/conftest.py (FastAPI TestClient setup, autouse fixture pattern, `_stub_local_provider_probes`)
    - backend/tests/integration/db/conftest.py (Plan 02 — `pg_database_url`; the integration tests in this task use the real-app TestClient + InMemoryMessageStore + InMemoryConversationRepository overrides for speed)
    - backend/tests/fixtures/llm.py (MockLLM for chat-create flow)
    - backend/app/chat/deps.py (Phase 5 D-06 — `make_chat_run_context` and the back-door comment lines 1-12)
    - backend/app/tools/flight_search.py (full file — confirm `ctx.deps.flight_client` reads at line 360; confirm no module-attribute writes anywhere)
    - .planning/phases/05-pydanticai-migration/05-VERIFICATION.md (truth #5 — `_flight_client` back-door confirmed deleted in Phase 5)
    - .planning/phases/06-postgres-redis-docker-compose/06-VALIDATION.md (Per-Task Verification Map: REQ-p5-flight-client-di + REQ-p5-conversation-rename + REQ-p5-provider-info-split)
    - CLAUDE.md (path-based test selection)
  </read_first>
  <action>
    Create `backend/tests/integration/test_conversation_routes.py` (TestClient-based; uses the existing `MockLLM` + `InMemoryMessageStore` + `InMemoryConversationRepository` fixture overrides — no DB required for this file):
      - `test_post_chat_conversation_accepts_split_body`: log in (`POST /api/auth/token` against the test fixture user), `POST /api/chat/conversation` with `{"target":{"provider":"ollama","model":"qwen3"},"credentials":{"base_url":"http://localhost:11434","api_key":null}}`; assert 201 + response carries `conversation_id`, `provider`, `model`.
      - `test_post_chat_conversation_rejects_legacy_flat_shape`: same auth, `POST /api/chat/conversation` with the legacy `{"provider":"ollama","model":"qwen3","base_url":"http://localhost:11434"}` body; assert 422 (FastAPI rejects the missing-target wrapper). Also assert the error detail mentions `target` (Pydantic v2 location-aware error).
      - `test_post_chat_conversation_validates_credentials_ssrf_through_split`: `POST /api/chat/conversation` with `{"target":{"provider":"ollama","model":"qwen3"},"credentials":{"base_url":"http://example.com"}}`; assert 422 with detail mentioning the SSRF allowlist message.
      - `test_post_chat_conversation_oversize_api_key_rejected`: same shape, `credentials.api_key` = `"x" * 257`; assert 422.
      - `test_legacy_session_routes_return_404`: assert all four legacy paths return 404: `POST /api/chat/session`, `DELETE /api/chat/session/abc`, `GET /api/chat/sessions`, `GET /api/chat/sessions/abc` (NOT 401 — auth is configured, the path is just unknown).
      - `test_get_chat_conversations_lists_user_conversations`: create two conversations via the renamed POST, then `GET /api/chat/conversations`; assert response contains exactly two entries each with `conversation_id`, `provider`, `model`, `created_at`, `first_message_preview`.
      - `test_delete_chat_conversation_returns_204_and_404_for_unknown`: create + delete returns 204; deleting same id again returns 404 with the ownership-shape message (Phase 6 PATTERNS.md §Ownership 404-shape).
    Create `backend/tests/integration/test_providers_endpoint.py`:
      - `test_get_providers_returns_local_and_cloud_discriminated_shapes`: `GET /api/providers`; assert `body["ollama"]["type"] == "local"`, `body["ollama"]["base_url"]` is a non-empty str (matches `settings.ollama_base_url`); assert `body["openai"]["type"] == "cloud"`, `body["openai"]["api_key_configured"]` is a bool; assert `"api_key" not in body["openai"]` (D-09 lock — bare api_key never crosses the wire).
      - `test_get_providers_local_entries_carry_base_url_field_only`: assert `set(body["lmstudio"].keys()) == {"type","available","models","base_url"}`.
      - `test_get_providers_cloud_entries_carry_api_key_configured_field_only`: assert `set(body["anthropic"].keys()) == {"type","available","models","api_key_configured"}`.
    Create or extend `backend/tests/unit/tools/test_flight_search_no_backdoor.py` (REQ-p5-flight-client-di lock):
      - if the file exists from Phase 5, ADD a new test method to it; if it does not exist, create the file with both the legacy Phase-5 assertion and the new Phase-6 forensic assertion below.
      - `test_search_flights_module_has_no_flight_client_attribute`: `import app.tools.flight_search as fs; assert not hasattr(fs, "_flight_client"); assert not hasattr(fs.search_flights, "_flight_client")` — locks the back-door at the module level.
      - `test_no_backdoor_assignments_or_getattrs_in_production_code`: forensic test using `subprocess.run(["rg", "-n", "search_flights\\._flight_client\\s*=|getattr\\(search_flights[^)]*_flight_client", "backend/app"], capture_output=True, text=True, check=False)` — assert returncode is non-zero (rg returns 1 when no matches found) AND stdout is empty. This is a regression lock ONLY for the prohibited shapes; the legitimate `self._flight_client` attribute on `ChatService` is not matched by the regex.
      - `test_chat_run_context_carries_flight_client_via_deps`: import `app.chat.deps.make_chat_run_context`; assert that the produced `RunContext` exposes `deps.flight_client` (or the equivalent attribute — adapt to the Phase 5 deps shape).
    Path-based selection: integration tests under `tests/integration/`, unit tests under `tests/unit/tools/`. No `@pytest.mark.*` markers per CLAUDE.md.
  </action>
  <verify>
    <automated>cd backend &amp;&amp; uv run pytest tests/integration/test_conversation_routes.py tests/integration/test_providers_endpoint.py tests/unit/tools/test_flight_search_no_backdoor.py -x --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - `test_legacy_session_routes_return_404` passes — all four legacy `/api/chat/sessions*` paths return 404.
    - `test_post_chat_conversation_rejects_legacy_flat_shape` passes — flat `{provider, model, base_url, api_key}` body returns 422 with `target` mentioned in the error detail.
    - `test_get_providers_returns_local_and_cloud_discriminated_shapes` passes; `api_key` field is absent from cloud-provider response payloads.
    - `test_search_flights_module_has_no_flight_client_attribute` passes; `test_no_backdoor_assignments_or_getattrs_in_production_code` passes (`rg` reports zero matches for the prohibited shapes).
    - `test_chat_run_context_carries_flight_client_via_deps` passes — confirms Phase 5 D-06 RunContext path is intact.
    - All seven integration tests + three unit tests pass deterministically; no test depends on a live Postgres (in-memory overrides handle persistence).
  </acceptance_criteria>
  <done>End-to-end coverage for renamed routes, both DTO splits, and the flight-client back-door regression lock; REQ-p5-flight-client-di is closed by passing test rather than absence-of-evidence.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → `POST /api/chat/conversation` | Untrusted JSON body crosses; `ConversationCreateRequest` Pydantic validators are the gate (SSRF allowlist + api_key length cap) |
| `GET /api/providers` → Browser | Server-side knowledge of API-key presence crosses as `api_key_configured: bool` only — never the key itself (D-09 lock from Phase 5) |
| Server-side rename window | During the rename, any drift between backend wire field name and frontend type imports breaks the SSE stream — coordinated atomic PR via 06-05a + 06-05b sequencing in Wave 5 (RESEARCH OQ-5) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-05a-01 | Tampering | `ProviderCredentials.base_url` SSRF | mitigate | Validators relocated VERBATIM from `SessionCreateRequest` (per Task 2 acceptance criterion) — same `{localhost, 127.0.0.1, host.docker.internal}` allowlist + http/https-only scheme guard. Test `test_provider_credentials_ssrf_allowlist` proves no regression. |
| T-06-05a-02 | Information Disclosure | `CloudProviderInfo` response | mitigate | Class declares `api_key_configured: bool` with no `api_key` field; integration test `test_get_providers_cloud_entries_carry_api_key_configured_field_only` asserts the response shape's key set excludes `api_key`. The Phase 5 D-09 lock (api_key in session memory only — never persisted, never logged) carries forward unchanged. |
| T-06-05a-03 | Spoofing | `ConversationCreateRequest.credentials.api_key` | mitigate | Length cap (256 chars) + whitespace-strip + empty-to-None normalisation, relocated from `SessionCreateRequest._strip_and_bound_api_key` byte-equivalent. Defensive against credential injection-by-padding. |
| T-06-05a-04 | Tampering | Rename window leaving inconsistent client/server contract | mitigate | 06-05a + 06-05b land in a single atomic PR (RESEARCH OQ-5). Backend wire-format golden test (`test_stream_event_wire_compat.py`) regenerates with `conversation_id` LAST; integration test `test_legacy_session_routes_return_404` proves the legacy paths are GONE (not silently aliased). The one failure mode is `master` between 06-05a and 06-05b commits — execute-phase MUST land both as a single squash. |
| T-06-05a-05 | Elevation of Privilege | Renamed routes — auth coverage | mitigate | The PATTERNS.md §Ownership 404-shape pattern is preserved verbatim through the rename (lines 86-93 of pre-rename routes.py). Test `test_delete_chat_conversation_returns_204_and_404_for_unknown` locks the ownership-shape 404 (a non-owner cannot probe for conversation existence by status code). All renamed handlers retain `Depends(get_current_active_user)`. |
| T-06-05a-06 | Repudiation | Phase 5 `_flight_client` back-door regression | mitigate | Test `test_no_backdoor_assignments_or_getattrs_in_production_code` runs `rg` against `backend/app` for the prohibited assignment + getattr shapes; on regression, the test fails loudly. Combined with `test_search_flights_module_has_no_flight_client_attribute`, REQ-p5-flight-client-di is locked by passing tests rather than absence-of-evidence. |
| T-06-05a-SC | Tampering | npm/pip/cargo installs | accept | No new packages installed in this plan; all dependencies pinned in Plan 01. Audit table covers them. |
</threat_model>

<verification>
- `cd backend && uv run pytest tests/unit/chat/test_stream_event_wire_compat.py tests/unit/chat/test_conversation_create_request_split.py tests/unit/test_provider_info_split.py tests/unit/tools/test_flight_search_no_backdoor.py tests/integration/test_conversation_routes.py tests/integration/test_providers_endpoint.py -x` passes.
- `cd backend && uv run pytest tests/unit tests/integration -x --tb=short` (full unit + integration regression) passes — every Phase 5-era chat / providers test compiles and passes after rename.
- `cd backend && uv run mypy app/ tests/` passes under strict mode.
- `cd backend && uv run ruff check app/ tests/` passes.
- `rg --no-filename 'session_id|SessionId' backend/app | grep -v 'auth/' | grep -v 'JWT\|jwt\|expir' | grep -v 'SessionLLMConfig\|SessionCreateError' | grep -v '^\s*#'` returns zero matches.
- `rg 'search_flights\._flight_client\s*=|getattr\(search_flights[^)]*_flight_client' backend/` returns zero matches.
</verification>

<success_criteria>
- `session` → `conversation` rename complete on backend production code; auth-side `session` (JWT lifetime) preserved per D-03.
- `SessionCreateRequest` deleted; `ConversationTarget` + `ProviderCredentials` + `ConversationCreateRequest` ship with relocated (byte-equivalent) SSRF + length validators.
- `ProviderInfo` deleted; `LocalProviderInfo` + `CloudProviderInfo` + `ProviderInfoResponse` ship with `api_key_configured: bool` (cloud) and required `base_url: str` (local).
- SSE wire format emits `conversation_id` LAST per StreamEvent subclass; the wire-compat golden test passes with the new field name.
- REQ-p5-flight-client-di is locked: forensic test asserts no `search_flights._flight_client = ...` or `getattr(search_flights, "_flight_client", ...)` remains; the legitimate `ChatService._flight_client` attribute is the only `_flight_client` token in `backend/app/`.
- The four renamed routes (`/api/chat/conversation`, `/api/chat/conversations`, `/api/chat/conversation/{id}`, `/api/chat/conversations/{id}`) work; legacy `/api/chat/sessions*` paths return 404.
- Frontend rename (06-05b) consumes the wire-format contract this plan publishes; both ship in the same atomic PR.
</success_criteria>

<output>
Create `.planning/phases/06-postgres-redis-docker-compose/06-05a-SUMMARY.md` when done.
</output>
</content>
</invoke>