"""Chat domain package (Phase 4.7 → Phase 5).

Houses ``ChatService`` (moved from ``app/chat.py`` in Phase 4.7) and the
discriminated-union event model hierarchy that replaces the monolithic
``StreamEvent`` class. Phase 5 adds the per-turn :class:`ChatDeps` DTO
(D-05) and the :class:`ConversationStore` ABC + first impl (D-08, D-11)
that PydanticAI's ``Agent`` consumes.
"""

from app.chat.deps import ChatDeps
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
from app.chat.store import ConversationStore, InMemoryConversationStore

__all__ = [
    "ChatDeps",
    "ChatService",
    "ContentEvent",
    "ConversationStore",
    "ErrorCode",
    "ErrorEvent",
    "InMemoryConversationStore",
    "StreamEvent",
    "ThinkingEvent",
    "ToolCallEvent",
    "ToolResultEvent",
]
