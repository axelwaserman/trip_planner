"""Wave 0 RED stub: ConversationStore ABC + InMemoryConversationStore round-trip.

Per CONTEXT.md D-08 + D-11 and the ``UserRepository(ABC)`` analog at
``backend/app/auth/repository.py:35-93``, ``ConversationStore`` is the canonical
ABC + first-impl pattern. Phase 6 will swap ``InMemoryConversationStore`` for
``PostgresConversationStore`` via FastAPI DI override.

All store methods are ``async def`` per CLAUDE.md "all I/O must be ``async def``"
(Phase 6's PG impl is naturally async; Phase 5's in-memory impl is
async-but-uncontended). Storage type is ``list[ModelMessage]`` from
``pydantic_ai.messages``.

This file collects cleanly via ``pytest.importorskip`` until Wave 1 creates
``app/chat/store.py`` and the ``pydantic-ai`` dep lands in Wave 4.
"""

import inspect

import pytest

# pydantic-ai is added in Wave 4; pytest.importorskip lets the file collect today.
pai_messages = pytest.importorskip("pydantic_ai.messages")
ModelMessage = pai_messages.ModelMessage  # noqa: F401  # imported for type-shape assertion below

store_module = pytest.importorskip("app.chat.store")
ConversationStore = store_module.ConversationStore
InMemoryConversationStore = store_module.InMemoryConversationStore


def test_conversation_store_is_abc() -> None:
    """ConversationStore is an ``abc.ABC`` per CLAUDE.md "ABC, not Protocol"."""
    assert inspect.isabstract(ConversationStore) is True


async def test_inmemory_round_trip_append_and_load() -> None:
    """append() then load() returns the same messages, in order."""
    store = InMemoryConversationStore()
    # Use ModelRequest as a concrete ModelMessage subclass; the field shape
    # is opaque to the store (it just persists list[ModelMessage]).
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    msg = ModelRequest(parts=[UserPromptPart(content="hello")])
    await store.append("s1", [msg])

    loaded = await store.load("s1")
    assert isinstance(loaded, list)
    assert len(loaded) == 1


async def test_load_empty_returns_empty_list() -> None:
    """load() for an unknown session returns an empty list, never raises."""
    store = InMemoryConversationStore()
    loaded = await store.load("never-existed")
    assert loaded == []


async def test_delete_removes_session() -> None:
    """delete() drops the session; subsequent load() returns []."""
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    store = InMemoryConversationStore()
    await store.append("s1", [ModelRequest(parts=[UserPromptPart(content="hi")])])
    await store.delete("s1")
    assert await store.load("s1") == []


async def test_list_for_user_returns_session_ids() -> None:
    """list_for_user(user_id) returns the user's ChatSessionInfo entries.

    The exact ChatSessionInfo shape is asserted via attribute access on the
    returned items (per CONTEXT.md D-22, D-27 — it carries ``session_id``,
    ``provider``, ``model``, ``created_at``, ``first_message_preview``).
    For the Wave 0 stub, we only assert the call returns a list — the
    Wave 1 impl is expected to be empty for a fresh store.
    """
    store = InMemoryConversationStore()
    sessions = await store.list_for_user("user-1")
    assert isinstance(sessions, list)
