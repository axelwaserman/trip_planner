"""Unified routes for Trip Planner API."""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.auth.routes import get_current_active_user
from app.auth.models import User
from app.chat import ChatService
from app.chat.models import (
    ChatRequest,
    ChatSessionHistoryResponse,
    ChatSessionsListResponse,
    ErrorCode,
    ErrorEvent,
    RetryRequest,
    SessionCreateRequest,
)
from app.config import settings
from app.llm.errors import ProbeError, ProbeErrorCode
from app.llm.factory import LLMProviderFactory, SessionLLMConfig
from app.providers.models import (
    ProviderInfo,
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


@router.post("/api/chat", response_class=StreamingResponse)
async def chat(
    request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """Chat endpoint with streaming responses.

    Accepts a chat message and session ID, returns a stream of events including
    AI responses, tool calls, and tool results.

    Per CR-02: the route verifies that ``request.session_id`` exists AND is
    owned by ``current_user`` before any history mutation or model call.
    Non-owner / missing-session both surface as 404 (same shape) so a caller
    cannot probe for session existence by status code. This stops a
    horizontal privilege escalation where Alice's valid token could read /
    write Bob's session history just by guessing the UUID.

    Args:
        request: ChatRequest with message and session_id
        chat_service: Injected ChatService instance
        current_user: Authenticated caller; must own the session.

    Returns:
        StreamingResponse with server-sent events

    Raises:
        HTTPException: 404 if session doesn't exist or is owned by another
            user; 500 surfaces internally as an SSE error event.
    """
    # Ownership check (CR-02). Same 404 shape on missing-vs-not-owner so
    # a non-owner cannot probe for session existence by status code.
    metadata = chat_service._metadata.get(request.session_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )

    async def event_generator() -> AsyncGenerator[str]:
        """Generate server-sent events from chat stream."""
        try:
            async for event in chat_service.chat_stream(
                session_id=request.session_id,
                message=request.message,
            ):
                # Format as server-sent event
                yield f"data: {event.model_dump_json()}\n\n"

        except ValueError:
            # Defensive: the route boundary already 404s missing sessions
            # (CR-02). This catch covers a narrow race where the session is
            # deleted between the boundary check and chat_stream's first
            # history read.
            error_event = ErrorEvent(
                error_code=ErrorCode.session_error,
                message="Session not found or expired.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                session_id=request.session_id,
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
            logger.exception("chat_stream failed for session %s", request.session_id)
            error_event = ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Sorry, something went wrong. Please try again.",
                retryable=False,
                tool_name=None,
                raw_detail=None,  # No exc str here — logger already captured it
                session_id=request.session_id,
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
    """Replay the last tool invocation for ``request.session_id``.

    CONTEXT.md D-07/D-08/D-09: reads ``_metadata[session_id]["last_tool_invocation"]``
    and re-streams the full LLM turn (tool_call → tool_result → reasoning → final
    response). Same CR-02 ownership pattern as POST /api/chat: 404 on missing-or-
    not-owner so a non-owner cannot probe for session existence.

    Returns:
        StreamingResponse with server-sent events (same SSE format as POST /api/chat).

    Raises:
        HTTPException: 404 if session doesn't exist or is owned by another user
            (same shape — prevents session-existence probing, mirrors CR-02).
        HTTPException: 422 if no tool invocation has been recorded yet for the session
            (requires at least one prior chat turn that triggered a tool call).
    """
    # CR-02 ownership check — same shape as POST /api/chat: 404 on missing-or-not-owner.
    # A non-owner receives the same 404 as a missing session to avoid leaking session
    # existence via status code differences (horizontal privilege escalation, T-04.7-04).
    metadata = chat_service._metadata.get(request.session_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )

    # 422 when no tool invocation has been recorded for the session (D-07).
    # Surfaces as Unprocessable Entity so the frontend can distinguish "no prior
    # tool call" (user error) from "missing session" (404 ownership failure).
    last_inv = metadata.get("last_tool_invocation")
    if last_inv is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No retryable tool invocation found for this session.",
        )

    # D-09: re-stream the full LLM turn. The agent already has the prior
    # conversation in its history (Plan 01 persists user turns upfront), so a
    # short directive triggers the same tool-calling loop that produced the
    # original invocation. The session's bound provider and tool set are
    # unchanged — only the prompt changes.
    replay_message = f"Please retry the previous {last_inv['tool_name']} call."

    async def event_generator() -> AsyncGenerator[str]:
        """Generate server-sent events from the retry stream."""
        try:
            async for event in chat_service.chat_stream(
                message=replay_message,
                session_id=request.session_id,
                persist_user_message=False,
            ):
                yield f"data: {event.model_dump_json()}\n\n"

        except ValueError:
            # Defensive: narrow race where the session is deleted between the
            # ownership check above and chat_stream's first history read.
            error_event = ErrorEvent(
                error_code=ErrorCode.session_error,
                message="Session not found or expired.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                session_id=request.session_id,
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

        except Exception:
            # CR-05: same static-message guarantee as POST /api/chat — no
            # exception text leaks over the SSE wire. The ApiKeyScrubber
            # redacts key-shaped substrings before the server-side log formats.
            logger.exception("retry_tool_call stream failed for session %s", request.session_id)
            error_event = ErrorEvent(
                error_code=ErrorCode.stream_error,
                message="Sorry, something went wrong. Please try again.",
                retryable=False,
                tool_name=None,
                raw_detail=None,
                session_id=request.session_id,
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


@router.post("/api/chat/session", status_code=status.HTTP_201_CREATED)
async def create_session(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: SessionCreateRequest | None = None,
) -> dict[str, str]:
    """Create a new chat session with optional provider/model selection.

    Generates a new session ID and initializes chat history for that session.
    Optionally accepts provider, model, base_url, and api_key fields per D-24.
    The provider's ``validate_config`` runs inline inside
    :meth:`ChatService.create_session`; on probe failure the structured
    :class:`app.llm.errors.ProbeError` surfaces as 502 (provider_unreachable)
    or 400 (everything else) — the 4.2 wire contract is preserved bit-for-bit.

    Model validation note (UAT round-3): for local providers (``ollama``,
    ``lmstudio``) we DO NOT enforce a route-level model whitelist — the
    per-provider probe owns that decision and surfaces a structured
    ``MODEL_NOT_INSTALLED`` ProbeError when the daemon doesn't have the
    requested model. The previous behaviour rejected legitimate
    daemon-installed models (e.g. ``qwen3.5:9b``) that weren't in the
    curated frozen list. Cloud providers (``openai``, ``anthropic``) still
    use the curated list since they have no live probe today.

    Args:
        request: Session creation request with optional provider/model/base_url/api_key.
        chat_service: Injected ChatService instance.

    Returns:
        Dictionary with ``session_id``, ``provider``, and ``model`` fields.
    """
    if request is None:
        request = SessionCreateRequest()

    # Defense-in-depth: validate provider name at the route boundary; the
    # model existence check is delegated to the per-provider probe for local
    # providers (see docstring + _resolve_allowed_cloud_models).
    if request.provider:
        providers = settings.get_available_providers()
        if request.provider not in providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider: {request.provider}. Available: {list(providers.keys())}",
            )

        if request.model:
            allowed_models = _resolve_allowed_cloud_models(provider=request.provider, curated=providers)
            if allowed_models is not None and request.model not in allowed_models:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid model {request.model} for provider {request.provider}",
                )

    # Default fallbacks live here (moved out of ChatService — SessionLLMConfig
    # requires non-None provider/model). NOTE: a follow-up phase wires
    # GET /api/providers to the dynamic /api/tags discovery cache; for now
    # settings.get_available_providers() above still returns the curated frozen
    # list for Ollama.
    config = SessionLLMConfig(
        provider=request.provider or settings.default_provider,
        model=request.model or settings.default_model,
        base_url=request.base_url,
        api_key=request.api_key,
    )

    session_id, probe_error = await chat_service.create_session(config, user_id=current_user.username)
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

    metadata = chat_service._metadata[session_id]
    return {
        "session_id": session_id,
        "provider": metadata["provider"],
        "model": metadata["model"],
    }


@router.delete("/api/chat/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Delete a chat session.

    Removes the session and its chat history from memory. Authentication is
    required (CR-01) and the session must belong to ``current_user`` — a
    non-owner gets the same 404 as a missing session to avoid leaking
    session existence (mirror of the per-user partition pattern from
    ``GET /api/chat/sessions``).

    Args:
        session_id: Session ID to delete
        chat_service: Injected ChatService instance
        current_user: Authenticated caller; must own the session.

    Raises:
        HTTPException: If session doesn't exist or is owned by another user
            (both surface as 404).
    """
    metadata = chat_service._metadata.get(session_id)
    if metadata is None or metadata.get("user_id") != current_user.username:
        # Same 404 shape on missing-vs-not-owner so a non-owner cannot
        # probe for session existence by status code.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Delete the session
    chat_service._histories.pop(session_id, None)
    chat_service._metadata.pop(session_id, None)
    chat_service._bound_providers.pop(session_id, None)
    chat_service._last_activity.pop(session_id, None)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns basic health status. Can be extended to check dependencies
    (database, LLM availability, etc.) in the future.

    Returns:
        Dictionary with status field
    """
    return {"status": "healthy"}


# (Plan 04.5-06b — _LOCAL_PROVIDER_NAMES is now declared above the
# _resolve_allowed_models helper so the create_session route can reach it.)


@router.get("/api/providers")
async def get_providers(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    factory: Annotated[LLMProviderFactory, Depends(get_llm_factory)],
) -> dict[str, ProviderInfo]:
    """Get available LLM providers and their models (D-25).

    Local providers (``ollama``, ``lmstudio``) read their model list from the
    discovery cache populated by ``POST /api/providers/refresh``. On first
    load, the cache is empty for at least one local entry — we lazy-trigger a
    single ``factory.refresh_local_models()`` call and serve from the resulting
    cache. Cloud providers (``openai``, ``anthropic``) keep the curated static
    model list from :meth:`Settings.get_available_providers` — we don't probe
    cloud APIs here (would burn quota on every settings page load).

    Every entry now carries ``base_url``: populated from
    ``Settings.{provider}_base_url`` for local providers; ``None`` for cloud.
    Frontend consumers that ignore ``base_url`` continue to work — additive change.

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

    result: dict[str, ProviderInfo] = {}
    # Local providers: models from discovery cache, base_url from Settings.
    result["ollama"] = ProviderInfo(
        available=bool(cache.get("ollama", [])),
        models=cache.get("ollama", []),
        base_url=settings.ollama_base_url,
    )
    result["lmstudio"] = ProviderInfo(
        available=bool(cache.get("lmstudio", [])),
        models=cache.get("lmstudio", []),
        base_url=settings.lmstudio_base_url,
    )
    # Cloud providers: curated static list, base_url=None.
    for name in ("openai", "anthropic"):
        entry = curated[name]
        models_field = entry["models"]
        result[name] = ProviderInfo(
            available=bool(entry["available"]),
            models=list(models_field) if isinstance(models_field, list) else [],
            base_url=None,
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


@router.get("/api/chat/sessions", response_model=ChatSessionsListResponse)
async def list_chat_sessions(
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatSessionsListResponse:
    """List the authenticated user's active sessions (D-22, D-27).

    Per RESEARCH.md Open Question 5 (RESOLVED): sessions are partitioned by
    ``_metadata[session_id]['user_id']``. A user can only see their own sessions.
    """
    sessions = chat_service.list_sessions_for_user(current_user.username)
    return ChatSessionsListResponse(sessions=sessions)


@router.get(
    "/api/chat/sessions/{session_id}",
    response_model=ChatSessionHistoryResponse,
)
async def get_chat_session_history(
    session_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatSessionHistoryResponse:
    """Return the message history for a session the authenticated user owns.

    Used by the Sidebar's "RECENT CHATS" list — clicking a row navigates to
    ``/app?session=<id>`` and the frontend hits this endpoint to seed the
    chat with the prior turns plus the provider/model the session was bound
    to. Both "missing session" and "not your session" collapse to ``404``
    (same shape as missing) so existence isn't leaked across users — same
    pattern as ``DELETE /api/chat/session/{id}`` and the per-user partition
    on ``GET /api/chat/sessions``.
    """
    history = chat_service.get_history_for_user(session_id, user_id=current_user.username)
    if history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return history
