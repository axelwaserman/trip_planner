"""Wave 0 RED stub: ChatDeps frozen dataclass shape (D-05).

Per CONTEXT.md D-05, ``ChatDeps`` is a ``@dataclass(frozen=True)`` carrying
three per-turn fields used to inject dependencies through PydanticAI's
``RunContext``:

    @dataclass(frozen=True)
    class ChatDeps:
        flight_client: FlightAPIClient
        conversation_id: str
        user_id: str

This file collects cleanly via ``pytest.importorskip`` until Wave 1 creates
``app/chat/deps.py``. After Wave 1, ``importorskip`` resolves the module and
the assertions below run for real, turning RED → GREEN.
"""

import dataclasses
from typing import get_type_hints

import pytest

deps_module = pytest.importorskip("app.chat.deps")
ChatDeps = deps_module.ChatDeps


def test_chatdeps_is_frozen_dataclass() -> None:
    """ChatDeps is declared with ``@dataclass(frozen=True)`` per D-05."""
    assert dataclasses.is_dataclass(ChatDeps)
    assert ChatDeps.__dataclass_params__.frozen is True


def test_chatdeps_has_required_fields() -> None:
    """ChatDeps exposes flight_client, conversation_id, user_id (D-05 ordering)."""
    field_names = {f.name for f in dataclasses.fields(ChatDeps)}
    assert field_names == {"flight_client", "conversation_id", "user_id"}


def test_chatdeps_field_types() -> None:
    """ChatDeps annotations carry FlightAPIClient + str + str.

    Resolved annotations (via ``get_type_hints``) are used for resilience to
    string vs runtime-class form. The ``flight_client`` type is asserted by
    name match against ``FlightAPIClient`` (the ABC from
    ``app.tools.flight_client``); ``conversation_id`` and ``user_id`` are ``str``.
    """
    hints = get_type_hints(ChatDeps)
    assert hints["conversation_id"] is str
    assert hints["user_id"] is str
    # FlightAPIClient is an ABC; check by name to remain decoupled from
    # the import path.
    assert hints["flight_client"].__name__ == "FlightAPIClient"
