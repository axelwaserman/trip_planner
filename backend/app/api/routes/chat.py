"""Chat routes."""

import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.chat import ChatService, create_chat_service
from app.domain.chat import ChatRequest
from app.infrastructure.storage.session import SessionStore
from app.services.flight import FlightService

router = APIRouter()


def get_session_store(request: Request) -> SessionStore:
    """Dependency factory for session store.

    Args:
        request: FastAPI request object

    Returns:
        SessionStore instance from app state
    """
    return request.app.state.session_store


def get_flight_service(request: Request) -> FlightService:
    """Dependency factory for flight service.

    Args:
        request: FastAPI request object

    Returns:
        FlightService instance with injected flight client
    """
    from app.api.routes.flights import get_flight_service as _get_flight_service

    return _get_flight_service(request.app.state.flight_client)


def get_chat_service(
    flight_service: Annotated[FlightService, Depends(get_flight_service)],
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> ChatService:
    """Dependency factory for chat service.

    Args:
        flight_service: Injected FlightService
        session_store: Injected SessionStore

    Returns:
        ChatService instance
    """
    return create_chat_service(flight_service, session_store)


@router.post("/api/chat/session")
async def create_session(
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> dict[str, str]:
    """Create a new chat session for a browser tab.

    Returns:
        Dictionary with session_id

    Example:
        >>> POST /api/chat/session
        {"session_id": "550e8400-e29b-41d4-a716-446655440000"}
    """
    session = await session_store.create_session()
    return {"session_id": session.session_id}


@router.post("/api/chat")
async def chat(
    request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> StreamingResponse:
    """Streaming chat endpoint that returns Server-Sent Events.

    Args:
        request: Chat request with message and session_id
        chat_service: Injected ChatService
        session_store: Injected SessionStore

    Returns:
        StreamingResponse with SSE chunks

    Raises:
        HTTPException: 400 if session_id is missing
        HTTPException: 404 if session not found or expired
    """
    # Validate session_id is provided
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    # Validate session exists and is not expired
    session = await session_store.get_session(request.session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Session not found or expired. Create a new session."
        )

    # Update session activity
    session.touch()
    await session_store.update_session(session)

    async def event_generator() -> AsyncGenerator[str]:
        """Generate Server-Sent Events for streaming response."""
        try:
            session_id = None
            async for event in chat_service.chat_stream(request.message, request.session_id):
                session_id = event.session_id
                
                # Send different SSE events based on event_type
                if event.event_type == "tool_call":
                    data = json.dumps({
                        "type": "tool_call",
                        "session_id": session_id,
                        "metadata": event.metadata.model_dump() if event.metadata else None
                    })
                    yield f"data: {data}\n\n"
                elif event.event_type == "tool_result":
                    data = json.dumps({
                        "type": "tool_result",
                        "session_id": session_id,
                        "metadata": event.metadata.model_dump() if event.metadata else None
                    })
                    yield f"data: {data}\n\n"
                elif event.event_type == "thinking":
                    data = json.dumps({
                        "type": "thinking",
                        "chunk": event.chunk,
                        "session_id": session_id
                    })
                    yield f"data: {data}\n\n"
                elif event.event_type == "content":
                    data = json.dumps({
                        "type": "content",
                        "chunk": event.chunk,
                        "session_id": session_id
                    })
                    yield f"data: {data}\n\n"

            # Send done event
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
