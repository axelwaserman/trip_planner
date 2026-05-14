"""Unified routes for Trip Planner API."""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.routes.auth import User, get_current_active_user
from app.chat import ChatService
from app.config import settings
from app.models import ChatRequest, SessionCreateRequest, StreamEvent

router = APIRouter()


# Dependency injection for ChatService
async def get_chat_service() -> ChatService:
    """Get the chat service instance from app state.

    This dependency will be injected by FastAPI when the app is configured.
    """
    # This will be replaced by the actual chat service from app.state in main.py
    raise RuntimeError("ChatService not configured in app state")


@router.post("/api/chat", response_class=StreamingResponse)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    _current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """Chat endpoint with streaming responses.

    Accepts a chat message and session ID, returns a stream of events including
    AI responses, tool calls, and tool results.

    Args:
        request: ChatRequest with message and session_id
        chat_service: Injected ChatService instance

    Returns:
        StreamingResponse with server-sent events

    Raises:
        HTTPException: If session doesn't exist (404) or other errors occur (500)
    """

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
            # Session not found
            error_event = StreamEvent(
                chunk="",
                session_id=request.session_id,
                type="content",  # Use content for error messages
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

        except Exception as e:
            # Other errors
            error_event = StreamEvent(
                chunk=f"An error occurred: {str(e)}",
                session_id=request.session_id,
                type="content",
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


@router.post("/api/chat/session", status_code=status.HTTP_201_CREATED)
async def create_session(
    chat_service: ChatService = Depends(get_chat_service),
    request: SessionCreateRequest | None = None,
    _current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    """Create a new chat session with optional provider/model selection.

    Generates a new session ID and initializes chat history for that session.
    Optionally accepts provider and model selection to override defaults.

    Args:
        request: Session creation request with optional provider/model
        chat_service: Injected ChatService instance

    Returns:
        Dictionary with session_id, provider, and model fields
    """
    if request is None:
        request = SessionCreateRequest()

    # Validate provider and model if specified
    if request.provider:
        providers = settings.get_available_providers()
        if request.provider not in providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider: {request.provider}. Available: {list(providers.keys())}",
            )
        if not providers[request.provider]["available"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {request.provider} not available (missing API key)",
            )
        if request.model and request.model not in providers[request.provider]["models"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid model {request.model} for provider {request.provider}",
            )

    session_id = chat_service.create_session(
        provider=request.provider,
        model=request.model,
    )

    # Return session info including the resolved provider/model
    metadata = chat_service._metadata[session_id]
    return {
        "session_id": session_id,
        "provider": metadata["provider"],
        "model": metadata["model"],
    }


@router.delete("/api/chat/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    """Delete a chat session.

    Removes the session and its chat history from memory.

    Args:
        session_id: Session ID to delete
        chat_service: Injected ChatService instance

    Raises:
        HTTPException: If session doesn't exist (404)
    """
    # Check if session exists
    try:
        chat_service.get_session_history(session_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        ) from err

    # Delete the session
    if session_id in chat_service._histories:
        del chat_service._histories[session_id]
    if session_id in chat_service._metadata:
        del chat_service._metadata[session_id]
    if session_id in chat_service._last_activity:
        del chat_service._last_activity[session_id]


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns basic health status. Can be extended to check dependencies
    (database, LLM availability, etc.) in the future.

    Returns:
        Dictionary with status field
    """
    return {"status": "healthy"}


@router.get("/api/providers")
async def get_providers(
    _current_user: User = Depends(get_current_active_user),
) -> dict[str, dict[str, list[str] | bool]]:
    """Get available LLM providers and their models.

    Returns information about which providers are available (have credentials)
    and what models each provider supports.

    Returns:
        Dictionary mapping provider names to their configuration:
        {
            "ollama": {"available": True, "models": [...]},
            "openai": {"available": False, "models": [...]},
            ...
        }
    """
    return settings.get_available_providers()
