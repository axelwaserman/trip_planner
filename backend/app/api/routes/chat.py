"""Chat routes."""

import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.routes.flights import get_flight_service
from app.chat import ChatService, create_chat_service
from app.domain.chat import ChatRequest
from app.services.flight import FlightService

router = APIRouter()


def get_chat_service(
    flight_service: Annotated[FlightService, Depends(get_flight_service)],
) -> ChatService:
    """Dependency factory for chat service.

    Args:
        flight_service: Injected FlightService

    Returns:
        ChatService instance with tools
    """
    return create_chat_service(flight_service)


@router.post("/api/chat")
async def chat(
    request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    """Streaming chat endpoint that returns Server-Sent Events.

    Args:
        request: Chat request with message and optional session_id

    Returns:
        StreamingResponse with SSE chunks
    """

    async def event_generator() -> AsyncGenerator[str]:
        """Generate Server-Sent Events for streaming response."""
        try:
            session_id = None
            async for chunk, sid in chat_service.chat_stream(request.message, request.session_id):
                session_id = sid
                # Send chunk as SSE
                data = json.dumps({"chunk": chunk, "session_id": session_id})
                yield f"data: {data}\n\n"

            # Send done event
            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"
        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
