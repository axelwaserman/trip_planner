"""Per-turn dependency container for the PydanticAI chat agent (D-05).

Phase 5 closes the Phase 4.5 ``search_flights._flight_client = ...``
monkey-patch back-door (D-06 anti-pattern lock) by threading the
:class:`FlightAPIClient` through PydanticAI's ``RunContext[ChatDeps]``
mechanism. The chat tool's first parameter becomes
``ctx: RunContext[ChatDeps]`` and reads ``ctx.deps.flight_client`` instead
of ``getattr(search_flights, "_flight_client", None)``.

Frozen by design (per ``~/.claude/rules/python/coding-style.md`` immutability
preference + CLAUDE.md "tunable thresholds … on Settings, not module-level
constants" — and an immutable per-turn DTO is the canonical analog at the
chat layer). Constructed once per chat turn inside
``ChatService.chat_stream`` and discarded after the turn closes.

Phase 6 (PostgresConversationStore swap) does NOT change this DTO — only the
storage tier moves. The ``user_id`` field is the partition key carried
through to ``ConversationStore.list_for_user`` so the SQL impl can
constraint-check ownership at the DB level.
"""

from dataclasses import dataclass

from app.tools.flight_client import FlightAPIClient


@dataclass(frozen=True)
class ChatDeps:
    """Per-turn dependency container threaded through PydanticAI ``RunContext``.

    Three fields per CONTEXT.md D-05 — the canonical chat-turn dependency shape:

    - ``flight_client``: the abstract :class:`app.tools.flight_client.FlightAPIClient`
      instance (``MockFlightAPIClient`` in dev / tests; a real adapter in
      production). Closes the ``_flight_client`` back-door (D-06).
    - ``conversation_id``: server-generated UUID identifying the chat conversation;
      stamped on every emitted ``StreamEvent`` for SSE wire correlation.
    - ``user_id``: authenticated username (the JWT ``sub`` claim) — used as
      the per-user partition key for ``ConversationRepository.list_for_user``
      and any auth-gated tool downstream of ``ctx.deps``.

    Frozen so a tool cannot accidentally mutate ``ctx.deps`` mid-turn. The
    instance is constructed inside :meth:`app.chat.service.ChatService.chat_stream`
    once per turn and threaded into ``agent.iter(deps=...)``.
    """

    flight_client: FlightAPIClient
    conversation_id: str
    user_id: str
