"""Unified routes for Trip Planner API."""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.auth.models import User
from app.auth.routes import get_current_active_user
from app.chat import ChatService
from app.chat.models import (
    ChatConversationHistoryResponse,
    ChatConversationsListResponse,
    ChatRequest,
    ConversationCreateRequest,
    ConversationTarget,
    ErrorCode,
    ErrorEvent,
    RetryRequest,
)
from app.chat.repository import ConversationRepository
from app.chat.store import MessageStore
from app.config import settings
from app.llm.errors import ProbeErrorCode
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.providers.models import (
    CloudProviderInfo,
    LocalProviderInfo,
    ProviderInfoResponse,
    ProviderRefreshEntry,
    ProviderRefreshResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency injection for ChatService
async def get_chat_service() -> ChatService:
    """Get the chat service instance from app state.

    This dependency will be injected by FastAPI when the app is configured.
    """
    # This will be replaced by the actual chat service from app.state in main.py
    raise RuntimeError("ChatService not configured in app state")


# Dependency injection for LLMProviderFactory (Plan 04.5-06b — D-06 refresh).
async def get_llm_factory() -> LLMProviderFactory:
    """Get the LLM factory from app state.

    Replaced by the actual factory from app.state in main.py via dependency_overrides.
    """
    raise RuntimeError("LLMProviderFactory not configured in app state")


# Placeholder dependencies for the Phase 6 / Plan 06-04 lifespan-wired
# stores (CONTEXT.md D-05/D-06). The lifespan startup registers
# ``app.dependency_overrides[get_message_store] = ...`` and
# ``app.dependency_overrides[get_conversation_repo] = ...`` so these
# RuntimeError stubs are never executed in a real request — they exist as
# fail-fast guards so unconfigured boots crash loudly.
def get_message_store() -> MessageStore:
    """Placeholder dependency — overridden in main.py lifespan startup."""
    raise RuntimeError("MessageStore not configured")


def get_conversation_repo() -> ConversationRepository:
    """Placeholder dependency — overridden in main.py lifespan startup."""
    raise RuntimeError("ConversationRepository not configured")


@router.post("/api/chat", response_class=StreamingResponse)
async def chat(
    request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """Chat endpoint with streaming responses.

    Accepts a chat message and conversation ID, returns a stream of events including
    AI responses, tool calls, and tool results.

    Per CR-02: the route verifies that ``request.conversation_id`` exists AND is
    owned by ``current_user`` before any history mutation or model call.
    Non-owner / missing-conversation both surface as 404 (same shape) so a caller
    cannot probe for conversation existence by status code. This stops a
    horizontal privilege escalation where Alice's valid token could read /
    write Bob's conversation history just by guessing the UUID.

    Args:
        request: ChatRequest with message and conversation_id
        chat_service: Injected ChatService instance
        current_user: Authenticated caller; must own the conversation.

    Returns:
        StreamingResponse with server-sent events

    Raises:
        HTTPException: 404 if conversation doesn't exist or is owned by another
            user; 500 surfaces internally as an SSE error event.
    """
    # Ownership check (CR-02). Same 404 shape on missing-vs-not-owner so
    # a non-owner cannot probe for conversation existence by status code.
    metadata = chat_service._metadata.get(request.conversation_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {request.conversation_id} not found",
        )

    async def event_generator() -> AsyncGenerator[str]:
        """Generate server-sent events from chat stream."""
        try:
            async for event in chat_service.chat_stream(
                conversation_id=request.conversation_id,
                message=request.message,
            ):
                # Format as server-sent event. ``event`` is typed as the
                # ``StreamEvent`` marker ABC; the five concrete subclasses
                # (ContentEvent, ThinkingEvent, ToolCallEvent, ToolResultEvent,
                # ErrorEvent) all multi-inherit BaseModel and therefore expose
                # ``model_dump_json``. mypy can't see this on the bare ABC.
                yield f"data: {event.model_dump_json()}\n\n"  # type: ignore[attr-defined]

        except ValueError:
            # Defensive: the route boundary already 404s missing conversations
            # (CR-02). This catch covers a narrow race where the conversation is
            # deleted between the boundary check and chat_stream's first
            # history read.
            error_event = ErrorEvent(
                error_code=ErrorCode.session_error,
                message="Conversation not found or expired.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                conversation_id=request.conversation_id,
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

        except Exception:
            # CR-05: do NOT echo str(e) over the SSE wire. Upstream SDK
            # exceptions (httpx, OpenAI / Anthropic SDK, langchain) often
            # carry internal URLs, file paths, model ids, and partial
            # payloads in their str() — leaking those to an authenticated-
            # but-not-trusted client is information disclosure. Log the full
            # exception server-side (the ApiKeyScrubber redacts any key-
            # shaped substrings before the formatter runs) and emit a
            # static, generic message to the client.
            logger.exception("chat_stream failed for conversation %s", request.conversation_id)
            error_event = ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Sorry, something went wrong. Please try again.",
                retryable=False,
                tool_name=None,
                raw_detail=None,  # No exc str here — logger already captured it
                conversation_id=request.conversation_id,
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        },
    )


@router.post("/api/chat/retry", response_class=StreamingResponse)
async def retry_tool_call(
    request: RetryRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """Replay the last tool invocation for ``request.conversation_id``.

    CONTEXT.md D-07/D-08/D-09: reads ``_metadata[conversation_id]["last_tool_invocation"]``
    and re-streams the full LLM turn (tool_call → tool_result → reasoning → final
    response). Same CR-02 ownership pattern as POST /api/chat: 404 on missing-or-
    not-owner so a non-owner cannot probe for conversation existence.

    Returns:
        StreamingResponse with server-sent events (same SSE format as POST /api/chat).

    Raises:
        HTTPException: 404 if conversation doesn't exist or is owned by another user
            (same shape — prevents conversation-existence probing, mirrors CR-02).
        HTTPException: 422 if no tool invocation has been recorded yet for the conversation
            (requires at least one prior chat turn that triggered a tool call).
    """
    # CR-02 ownership check — same shape as POST /api/chat: 404 on missing-or-not-owner.
    # A non-owner receives the same 404 as a missing conversation to avoid leaking
    # conversation existence via status code differences (horizontal privilege escalation, T-04.7-04).
    metadata = chat_service._metadata.get(request.conversation_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {request.conversation_id} not found",
        )

    # 422 when no tool invocation has been recorded for the conversation (D-07).
    # Surfaces as Unprocessable Entity so the frontend can distinguish "no prior
    # tool call" (user error) from "missing conversation" (404 ownership failure).
    last_inv = metadata.get("last_tool_invocation")
    if last_inv is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No retryable tool invocation found for this conversation.",
        )

    # D-09: re-stream the full LLM turn. The agent already has the prior
    # conversation in its history (Plan 01 persists user turns upfront), so a
    # short directive triggers the same tool-calling loop that produced the
    # original invocation. The conversation's bound provider and tool set are
    # unchanged — only the prompt changes.
    replay_message = f"Please retry the previous {last_inv['tool_name']} call."

    async def event_generator() -> AsyncGenerator[str]:
        """Generate server-sent events from the retry stream."""
        try:
            async for event in chat_service.chat_stream(
                message=replay_message,
                conversation_id=request.conversation_id,
                persist_user_message=False,
            ):
                # See note on the corresponding line in chat_stream above —
                # StreamEvent is a marker ABC; concrete subclasses all expose
                # model_dump_json via their BaseModel base.
                yield f"data: {event.model_dump_json()}\n\n"  # type: ignore[attr-defined]

        except ValueError:
            # Defensive: narrow race where the conversation is deleted between the
            # ownership check above and chat_stream's first history read.
            error_event = ErrorEvent(
                error_code=ErrorCode.session_error,
                message="Conversation not found or expired.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                conversation_id=request.conversation_id,
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

        except Exception:
            # CR-05: same static-message guarantee as POST /api/chat — no
            # exception text leaks over the SSE wire. The ApiKeyScrubber
            # redacts key-shaped substrings before the server-side log formats.
            logger.exception("retry_tool_call stream failed for conversation %s", request.conversation_id)
            error_event = ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Sorry, something went wrong. Please try again.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                conversation_id=request.conversation_id,
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        },
    )


# Plan 04.5-06b — local providers Ollama and LM Studio share the discovery
# cache populated by POST /api/providers/refresh and lazy-read by GET /api/providers.
_LOCAL_PROVIDER_NAMES: tuple[str, ...] = ("ollama", "lmstudio")


def _resolve_allowed_cloud_models(
    *,
    provider: str,
    curated: dict[str, dict[str, list[str] | bool]],
) -> list[str] | None:
    """Allowed-model list for cloud providers (curated frozen list).

    Local providers (``ollama``, ``lmstudio``) do NOT use route-level model
    validation — a request with an unknown model passes the route layer and
    the per-provider ``validate_config`` returns the structured
    ``MODEL_NOT_INSTALLED`` ProbeError on probe. That structured error has
    actionable copy + inline-code chips (``ollama pull <model>``) the frontend
    SelectorErrorBanner renders. A route-level "Invalid model" string would
    short-circuit the probe and lose that UX, AND would block legitimate
    daemon-side models that aren't in any curated list (the bug this UAT
    round-3 fix addresses).

    For cloud providers there is no live probe yet (deferred to the
    Test-connection plan), so the curated frozen list still governs —
    typos surface as a 400 here rather than burning quota.
    """
    if provider in _LOCAL_PROVIDER_NAMES:
        return None  # Probe owns this — see docstring.
    models = curated[provider]["models"]
    return list(models) if isinstance(models, list) else None


@router.post("/api/chat/conversation", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: ConversationCreateRequest | None = None,
) -> dict[str, str]:
    """Create a new chat conversation with optional provider/model selection.

    Generates a new conversation ID and initializes chat history for that
    conversation. Optionally accepts a nested ``target`` (provider/model) and
    ``credentials`` (base_url/api_key) per REQ-p5-session-create-request-split.
    The provider's ``validate_config`` runs inline inside
    :meth:`ChatService.create_session`; on probe failure the structured
    :class:`app.llm.errors.ProbeError` surfaces as 502 (provider_unreachable)
    or 400 (everything else) — the 4.2 wire contract is preserved bit-for-bit.

    Model validation note (UAT round-3): for local providers (``ollama``,
    ``lmstudio``) we DO NOT enforce a route-level model whitelist — the
    per-provider probe owns that decision and surfaces a structured
    ``MODEL_NOT_INSTALLED`` ProbeError when the daemon doesn't have the
    requested model. Cloud providers (``openai``, ``anthropic``) still use
    the curated list since they have no live probe today.

    Args:
        request: Conversation creation request with optional target + credentials.
        chat_service: Injected ChatService instance.

    Returns:
        Dictionary with ``conversation_id``, ``provider``, and ``model`` fields.
    """
    target = request.target if request is not None else ConversationTarget()
    credentials = request.credentials if request is not None else None

    # Defense-in-depth: validate provider name at the route boundary; the
    # model existence check is delegated to the per-provider probe for local
    # providers (see docstring + _resolve_allowed_cloud_models).
    if target.provider:
        providers = settings.get_available_providers()
        if target.provider not in providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider: {target.provider}. Available: {list(providers.keys())}",
            )

        if target.model:
            allowed_models = _resolve_allowed_cloud_models(provider=target.provider, curated=providers)
            if allowed_models is not None and target.model not in allowed_models:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid model {target.model} for provider {target.provider}",
                )

    # Default fallbacks live here (moved out of ChatService — SessionLLMConfig
    # requires non-None provider/model). Build the internal SessionLLMConfig
    # from the split DTO; the LLM-factory contract is unchanged.
    config = SessionLLMConfig(
        provider=target.provider or settings.default_provider,
        model=target.model or settings.default_model,
        base_url=credentials.base_url if credentials is not None else None,
        api_key=credentials.api_key if credentials is not None else None,
    )

    conversation_id, probe_error = await chat_service.create_session(config, user_id=current_user.username)
    if probe_error is not None:
        # Network-level reachability failures map to 502 Bad Gateway; everything
        # else (model not installed, missing API key) is the user's misconfig
        # and surfaces as 400 Bad Request. 4.2 wire contract preserved.
        probe_status = (
            status.HTTP_502_BAD_GATEWAY
            if probe_error.error == ProbeErrorCode.PROVIDER_UNREACHABLE
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=probe_status, detail=probe_error.model_dump())

    metadata = chat_service._metadata[conversation_id]
    return {
        "conversation_id": conversation_id,
        "provider": metadata["provider"],
        "model": metadata["model"],
    }


@router.delete("/api/chat/conversation/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Delete a chat conversation.

    Removes the conversation and its chat history from memory. Authentication is
    required (CR-01) and the conversation must belong to ``current_user`` — a
    non-owner gets the same 404 as a missing conversation to avoid leaking
    conversation existence (mirror of the per-user partition pattern from
    ``GET /api/chat/conversations``).

    Args:
        conversation_id: Conversation ID to delete
        chat_service: Injected ChatService instance
        current_user: Authenticated caller; must own the conversation.

    Raises:
        HTTPException: If conversation doesn't exist or is owned by another user
            (both surface as 404).
    """
    metadata = chat_service._metadata.get(conversation_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        # Same 404 shape on missing-vs-not-owner so a non-owner cannot
        # probe for conversation existence by status code.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Phase 5 / Plan 05-04: ``_histories`` + ``_bound_providers`` retired in
    # favour of ``_agents`` + the ``ConversationStore`` seam. ``delete_conversation``
    # awaits the store and prunes the per-conversation dicts.
    await chat_service.delete_conversation(conversation_id)


@router.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    """Health check endpoint.

    Phase 7 / Plan 07-05 (D-06): surfaces the active flight provider
    (``"real"`` when ``AmadeusFlightClient`` is wired, ``"mock"`` when the
    auto-fallback path picked ``MockFlightAPIClient``). The lifespan stashes
    the choice on ``app.state.flight_provider`` before yield; the
    ``getattr(..., "mock")`` default is a defensive fallback for invocations
    that bypass lifespan (no real CI path does).

    Returns:
        Dictionary with ``status`` and ``flight_provider`` fields.
    """
    flight_provider = getattr(request.app.state, "flight_provider", "mock")
    return {"status": "healthy", "flight_provider": flight_provider}


# (Plan 04.5-06b — _LOCAL_PROVIDER_NAMES is now declared above the
# _resolve_allowed_models helper so the create_conversation route can reach it.)


@router.get("/api/providers")
async def get_providers(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    factory: Annotated[LLMProviderFactory, Depends(get_llm_factory)],
) -> dict[str, ProviderInfoResponse]:
    """Get available LLM providers and their models (D-25).

    Local providers (``ollama``, ``lmstudio``) read their model list from the
    discovery cache populated by ``POST /api/providers/refresh``. On first
    load, the cache is empty for at least one local entry — we lazy-trigger a
    single ``factory.refresh_local_models()`` call and serve from the resulting
    cache. Cloud providers (``openai``, ``anthropic``) keep the curated static
    model list from :meth:`Settings.get_available_providers` — we don't probe
    cloud APIs here (would burn quota on every settings page load).

    Plan 06-05a (REQ-p5-provider-info-split) introduces a discriminated
    response: local entries are :class:`LocalProviderInfo` (``base_url`` is
    always present); cloud entries are :class:`CloudProviderInfo`
    (``api_key_configured: bool`` only — D-09 lock). The
    :data:`ProviderInfoResponse` alias drives Pydantic's discriminated-union
    serialization off the ``type`` field.

    The endpoint stays auth-protected via ``Depends(get_current_active_user)``.
    """
    cache: dict[str, list[str]] = request.app.state.provider_models_cache
    timestamps: dict[str, float] = request.app.state.provider_models_cache_timestamps
    now = time.time()

    # Lazy first-load: if any local provider has no cache entry yet, trigger a
    # one-shot discovery. Subsequent calls hit the cache regardless of TTL —
    # the explicit /refresh endpoint owns the re-discovery cadence.
    needs_lazy_load = any(name not in cache for name in _LOCAL_PROVIDER_NAMES)
    if needs_lazy_load:
        fresh = await factory.refresh_local_models()
        for name, models in fresh.items():
            cache[name] = [] if models is None else models
            timestamps[name] = now

    # Cloud providers — curated lists from Settings, no live probe.
    curated = settings.get_available_providers()

    result: dict[str, ProviderInfoResponse] = {}
    # Local providers: models from discovery cache, base_url from Settings.
    result["ollama"] = LocalProviderInfo(
        available=bool(cache.get("ollama", [])),
        models=cache.get("ollama", []),
        base_url=settings.ollama_base_url,
    )
    result["lmstudio"] = LocalProviderInfo(
        available=bool(cache.get("lmstudio", [])),
        models=cache.get("lmstudio", []),
        base_url=settings.lmstudio_base_url,
    )
    # Cloud providers: curated static list; api_key_configured derived from
    # Settings.{provider}_api_key (D-09 — bare api_key never crosses the wire).
    for name in ("openai", "anthropic"):
        entry = curated[name]
        models_field = entry["models"]
        result[name] = CloudProviderInfo(
            available=bool(entry["available"]),
            models=list(models_field) if isinstance(models_field, list) else [],
            api_key_configured=bool(getattr(settings, f"{name}_api_key", None)),
        )
    return result


# ----------------------------------------------------------------------------
# Plan 04.5-06b — three new endpoints (D-06, D-14, D-22, D-27)
# ----------------------------------------------------------------------------


@router.post("/api/providers/refresh", response_model=ProviderRefreshResponse)
async def refresh_providers(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    factory: Annotated[LLMProviderFactory, Depends(get_llm_factory)],
) -> ProviderRefreshResponse:
    """Re-discover all local providers in parallel; return enriched provider list (D-06).

    Unlike GET /api/providers (which uses TTL-gated lazy loading), this endpoint
    always calls factory.refresh_local_models() unconditionally — the user
    explicitly requested fresh data. On partial unreachable, returns 200 with
    the unreachable entries marked ``available=False`` and
    ``error="provider_unreachable"`` — clients show the marker rather than
    failing the whole settings page.
    """
    cache: dict[str, list[str]] = request.app.state.provider_models_cache
    timestamps: dict[str, float] = request.app.state.provider_models_cache_timestamps
    now = time.time()

    # Explicit refresh always re-discovers regardless of TTL. The user pressed
    # "Refresh" — they want current data, not a cached snapshot.
    fresh = await factory.refresh_local_models()
    for name, models in fresh.items():
        cache[name] = [] if models is None else models
        timestamps[name] = now

    # Build the response from cache. Mark unreachable when cache is empty
    # (a cache entry of [] means we just probed and the daemon didn't answer).
    entries: list[ProviderRefreshEntry] = []
    for name in _LOCAL_PROVIDER_NAMES:
        models = cache.get(name, [])
        available = bool(models)
        error = None if available else "provider_unreachable"
        entries.append(
            ProviderRefreshEntry(
                name=name,
                models=models,
                available=available,
                error=error,
            )
        )

    return ProviderRefreshResponse(providers=entries)


@router.get("/api/chat/conversations", response_model=ChatConversationsListResponse)
async def list_conversations(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatConversationsListResponse:
    """List the authenticated user's active conversations (D-22, D-27).

    Per RESEARCH.md Open Question 5 (RESOLVED): conversations are partitioned by
    ``_metadata[conversation_id]['user_id']``. A user can only see their own
    conversations.
    """
    conversations = await chat_service.list_conversations_for_user(current_user.username)
    return ChatConversationsListResponse(conversations=conversations)


@router.get(
    "/api/chat/conversations/{conversation_id}",
    response_model=ChatConversationHistoryResponse,
)
async def get_chat_conversation_history(
    conversation_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatConversationHistoryResponse:
    """Return the message history for a conversation the authenticated user owns.

    Used by the Sidebar's "RECENT CHATS" list — clicking a row navigates to
    ``/app?conversation=<id>`` and the frontend hits this endpoint to seed the
    chat with the prior turns plus the provider/model the conversation was bound
    to. Both "missing conversation" and "not your conversation" collapse to
    ``404`` (same shape as missing) so existence isn't leaked across users —
    same pattern as ``DELETE /api/chat/conversation/{id}`` and the per-user
    partition on ``GET /api/chat/conversations``.
    """
    history = await chat_service.get_history_for_user(conversation_id, user_id=current_user.username)
    if history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return history
