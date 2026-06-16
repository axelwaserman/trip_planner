"""Unit tests for :class:`InMemoryMessageStore` (Plan 06-03 Task 3).

Locks the observable contract every :class:`MessageStore` impl must satisfy:

- Round-trip via ``append`` + ``load`` returns the same ``ModelMessage`` list.
- ``load`` for an unknown conversation returns ``[]`` — never raises.
- ``append`` is immutable — the underlying stored list reference is replaced,
  not mutated, on each call (preserves the Phase 5 invariant).
- ``delete`` empties the conversation.
- ``first_user_message_preview`` truncates to 80 chars and returns ``None``
  for empty conversations (the CR-04 fix — no more ``getattr(_store)`` peek).
"""

from __future__ import annotations

from uuid import uuid4

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.chat.store import InMemoryMessageStore


async def test_append_then_load_roundtrips_messages() -> None:
    """append + load returns a 2-message list with the same parts and content."""
    # Arrange
    store = InMemoryMessageStore()
    conversation_id = uuid4()
    user_msg = ModelRequest(parts=[UserPromptPart(content="find me flights to LAX")])
    assistant_msg = ModelResponse(parts=[TextPart(content="Here are some options.")])

    # Act
    await store.append(conversation_id, [user_msg, assistant_msg])
    loaded = await store.load(conversation_id)

    # Assert
    assert len(loaded) == 2
    assert isinstance(loaded[0], ModelRequest)
    assert isinstance(loaded[0].parts[0], UserPromptPart)
    assert loaded[0].parts[0].content == "find me flights to LAX"
    assert isinstance(loaded[1], ModelResponse)
    assert isinstance(loaded[1].parts[0], TextPart)
    assert loaded[1].parts[0].content == "Here are some options."


async def test_load_returns_empty_list_for_unknown_conversation() -> None:
    """A brand-new UUID with no appended messages returns ``[]``, never raises."""
    # Arrange
    store = InMemoryMessageStore()
    unknown = uuid4()

    # Act
    loaded = await store.load(unknown)

    # Assert
    assert loaded == []


async def test_append_uses_immutable_concat_not_in_place() -> None:
    """The first appended-list reference must be replaced, not mutated.

    Captures the underlying list reference after the first append, then
    appends again. The first reference must still point to a 1-message list —
    if append() did ``existing.append(...)`` in place, the captured reference
    would now have 2 items.
    """
    # Arrange
    store = InMemoryMessageStore()
    conversation_id = uuid4()
    msg1 = ModelRequest(parts=[UserPromptPart(content="first")])
    msg2 = ModelRequest(parts=[UserPromptPart(content="second")])

    # Act — first append, capture the underlying list reference
    await store.append(conversation_id, [msg1])
    first_ref = store._store[conversation_id]
    assert len(first_ref) == 1

    # Append again — internal list should be REPLACED, not mutated
    await store.append(conversation_id, [msg2])

    # Assert — the captured reference still has only 1 message
    assert len(first_ref) == 1, "InMemoryMessageStore.append mutated the existing list in place"
    # And the new internal state is a different list object with both
    new_ref = store._store[conversation_id]
    assert new_ref is not first_ref
    assert len(new_ref) == 2


async def test_delete_drops_messages() -> None:
    """delete empties the conversation; load afterwards returns ``[]``."""
    # Arrange
    store = InMemoryMessageStore()
    conversation_id = uuid4()
    await store.append(conversation_id, [ModelRequest(parts=[UserPromptPart(content="hello")])])
    assert len(await store.load(conversation_id)) == 1

    # Act
    await store.delete(conversation_id)

    # Assert
    assert await store.load(conversation_id) == []


async def test_first_user_message_preview_returns_first_user_prompt() -> None:
    """preview returns the first UserPromptPart truncated to 80 chars."""
    # Arrange — a long content (>80 chars) so the truncation is observable
    store = InMemoryMessageStore()
    conversation_id = uuid4()
    long_content = "find flights to LAX please " * 5  # ~135 chars
    user_msg = ModelRequest(parts=[UserPromptPart(content=long_content)])
    assistant_msg = ModelResponse(parts=[TextPart(content="Here you go.")])
    await store.append(conversation_id, [user_msg, assistant_msg])

    # Act
    preview = await store.first_user_message_preview(conversation_id)

    # Assert — preview is exactly the first 80 chars of the user prompt
    assert preview is not None
    assert preview == long_content[:80]
    assert len(preview) == 80


async def test_first_user_message_preview_returns_none_when_empty() -> None:
    """preview returns ``None`` for an empty conversation (CR-04 fix)."""
    # Arrange
    store = InMemoryMessageStore()
    unknown = uuid4()

    # Act
    preview = await store.first_user_message_preview(unknown)

    # Assert
    assert preview is None
