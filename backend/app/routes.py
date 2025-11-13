"""Unified routes for Trip Planner API."""

from typing import AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.chat import ChatService
from app.models import ChatRequest, StreamEvent


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
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate server-sent events from chat stream."""
        try:
            async for event in chat_service.chat_stream(
                session_id=request.session_id,
                message=request.message,
            ):
                # Format as server-sent event
                yield f"data: {event.model_dump_json()}\n\n"
                
        except ValueError as e:
            # Session not found
            error_event = StreamEvent(
                chunk="",
                session_id=request.session_id,
                event_type="content",  # Use content for error messages
            )
            yield f"data: {error_event.model_dump_json()}\n\n"
            
        except Exception as e:
            # Other errors
            error_event = StreamEvent(
                chunk=f"An error occurred: {str(e)}",
                session_id=request.session_id,
                event_type="content",
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
) -> dict[str, str]:
    """Create a new chat session.
    
    Generates a new session ID and initializes chat history for that session.
    
    Args:
        chat_service: Injected ChatService instance
        
    Returns:
        Dictionary with session_id field
    """
    session_id = chat_service.create_session()
    return {"session_id": session_id}


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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    # Delete the session
    if session_id in chat_service._histories:
        del chat_service._histories[session_id]
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
