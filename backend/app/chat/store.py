"""Persistent chat conversation storage (D-08, D-11).

Phase 5 introduces a :class:`ConversationStore` ABC that abstracts the
``list[ModelMessage]`` round-trip used by the new PydanticAI-driven
:meth:`ChatService.chat_stream`. The Phase 5 in-memory implementation is
stateful only for the duration of the process; Phase 6 swaps in a
``PostgresConversationStore`` via FastAPI DI override (per the canonical
:class:`app.auth.repository.UserRepository` ABC + first-impl pattern).

Per D-09, session metadata (``provider``, ``model``, ``created_at``,
``last_activity``) lives on :class:`ChatService._metadata` — the store
deliberately does NOT carry it. ``list_for_user`` is therefore minimal in
Phase 5 (returns an empty list); ``ChatService`` composes the user-scoped
view by joining ``_metadata`` with the store's per-session contents. Phase 6
shifts ownership of the ``user_id → session_id`` index into SQL, at which
point ``list_for_user`` returns a populated list.

Per CLAUDE.md "all I/O must be ``async def``", every method is ``async def``
even though the in-memory impl is uncontended — Phase 6's PG impl is
naturally async, and the ABC must match that contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # pydantic_ai is added in Wave 4; using TYPE_CHECKING keeps this module
    # importable while Waves 1-3 land. ``ModelMessage`` is the PydanticAI
    # canonical message-history type — opaque to the store, which only
    # appends/reads list[ModelMessage] without inspecting field shape (D-11).
    from pydantic_ai.messages import ModelMessage

    # ChatSessionInfo is annotation-only (return type of list_for_user); moving
    # to TYPE_CHECKING avoids the runtime cycle through app.chat.__init__.
    from app.chat.models import ChatSessionInfo


class ConversationStore(ABC):
    """Abstract conversation store keyed by ``session_id`` (D-08).

    Phase 5 contract: persist a per-session ``list[ModelMessage]`` and expose
    minimal CRUD operations against it. Phase 6 swaps the in-memory impl for
    a Postgres-backed one via FastAPI DI override (the
    :class:`app.auth.repository.UserRepository` ABC + ``EnvUserRepository``
    pattern is the canonical analog).

    Per CONTEXT.md D-09 the store does NOT track session-level metadata
    (``provider``/``model``/timestamps) — that lives on
    :class:`app.chat.service.ChatService._metadata`. ``list_for_user``'s
    return type is :class:`ChatSessionInfo` for forward compatibility with
    Phase 6 where the SQL impl owns the user→sessions index and can return
    populated entries directly.
    """

    @abstractmethod
    async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Append ``messages`` to the session's history.

        Implementations MUST treat the existing history as immutable and
        produce a new list internally (per ``~/.claude/rules/common/coding-style.md``
        immutability rule). Append is the only mutation; in-place edits are
        not supported.

        Args:
            session_id: Server-generated session UUID; used as the storage key.
            messages: One or more ``ModelMessage`` instances to append. The
                list is opaque to the store — element shape is owned by
                PydanticAI.
        """
        ...

    @abstractmethod
    async def load(self, session_id: str) -> list[ModelMessage]:
        """Load the session's full message history.

        Args:
            session_id: Server-generated session UUID.

        Returns:
            A list of ``ModelMessage``; empty list when the session is
            unknown (the store NEVER raises for missing keys — per the
            ``UserRepository`` analog).
        """
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Remove the session's history. No-op for unknown ``session_id``.

        Args:
            session_id: Server-generated session UUID.
        """
        ...

    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[ChatSessionInfo]:
        """List sessions owned by ``user_id`` as :class:`ChatSessionInfo` entries.

        Phase 5 in-memory impl returns an empty list — the store does NOT
        track the ``user_id → session_id`` index (D-09 keeps that on
        ``ChatService._metadata``). Phase 6 ``PostgresConversationStore``
        owns this index in SQL and returns populated entries.

        Args:
            user_id: Authenticated username (the JWT ``sub`` claim).

        Returns:
            A list of :class:`ChatSessionInfo` entries; in Phase 5 always
            empty. ``ChatService.list_sessions`` composes the user-scoped
            view from its own ``_metadata`` dict regardless of this return.
        """
        ...


class InMemoryConversationStore(ConversationStore):
    """Phase 5 in-memory :class:`ConversationStore`.

    State lives in two private dicts:

    - ``_store: dict[str, list[ModelMessage]]`` — per-session message history.
    - The ``user_id → session_id`` index is intentionally NOT tracked here
      (D-09); :class:`app.chat.service.ChatService` composes user-scoped
      views from its own ``_metadata`` dict. Phase 6's
      ``PostgresConversationStore`` migrates that index into SQL with FK
      constraints on the ``user_id`` column.

    Round-trip via ``append`` then ``load`` returns a defensive copy of the
    stored list so callers cannot mutate the store's internal state — same
    invariant as :class:`app.auth.repository.EnvUserRepository.get_user`'s
    ``UserInDB`` returns.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[ModelMessage]] = {}

    async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
        """Append ``messages`` immutably (``existing + messages``)."""
        existing = self._store.get(session_id, [])
        # Immutable concat per coding-style.md — never `.append()` in place.
        self._store[session_id] = existing + messages

    async def load(self, session_id: str) -> list[ModelMessage]:
        """Return a defensive copy of the session's history (empty list when unknown)."""
        return list(self._store.get(session_id, []))

    async def delete(self, session_id: str) -> None:
        """Drop the session entry. ``dict.pop(..., None)`` makes this a no-op for unknowns."""
        self._store.pop(session_id, None)

    async def list_for_user(self, user_id: str) -> list[ChatSessionInfo]:
        """Phase 5: returns an empty list (D-09 keeps user-indexing on ChatService).

        Phase 6 ``PostgresConversationStore`` will own the ``user_id →
        session_id`` index in SQL and return populated entries; until then,
        :meth:`app.chat.service.ChatService.list_sessions` composes the
        user-scoped view from its own ``_metadata`` dict and ignores this
        return value.
        """
        return []
