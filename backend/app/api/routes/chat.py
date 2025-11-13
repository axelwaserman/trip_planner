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
        ChatService instance (uses global store for conversation history)
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
