"""Chat domain package (Phase 4.7).

Houses ``ChatService`` (moved from ``app/chat.py``) and the discriminated-union
event model hierarchy that replaces the monolithic ``StreamEvent`` class.
"""

from app.chat.models import (
    ContentEvent,
    ErrorCode,
    ErrorEvent,
    StreamEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.chat.service import ChatService

__all__ = [
    "ChatService",
    "ContentEvent",
    "ErrorCode",
    "ErrorEvent",
    "StreamEvent",
    "ThinkingEvent",
    "ToolCallEvent",
    "ToolResultEvent",
]
