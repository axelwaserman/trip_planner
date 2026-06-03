"""Wave 0 RED stub: anti-pattern lock for the ``_flight_client`` back-door (D-06).

Per CONTEXT.md D-06 + the explicit anti-pattern lock ("Don't keep
``search_flights._flight_client`` 'just in case'"), the Phase 4.x monkey-patched
attribute back-door must NOT coexist with PydanticAI's ``RunContext[ChatDeps]``
DI surface. The Wave 1 rewrite of ``app/tools/flight_search.py`` deletes the
``getattr(search_flights, '_flight_client', None)`` line and replaces it with
``ctx.deps.flight_client``.

This file is the regression guard. After Wave 1:

1. ``search_flights`` is a plain ``async def`` (no ``@tool`` decorator) — so
   ``inspect.signature`` works.
2. The first positional parameter is ``ctx: RunContext[ChatDeps]``.
3. ``search_flights._flight_client`` does NOT exist — there is no attribute
   side-channel.

These tests must continue to pass for the rest of the project's life. Re-adding
the back-door — even "temporarily" — flips them to RED and blocks merges.

Closes ARCHITECTURE.md "Monkey-Patched Tool Dependency" Known Tech Debt.
"""

import inspect

from app.tools.flight_search import search_flights


def test_search_flights_has_no_flight_client_attribute() -> None:
    """The Phase 4.x ``_flight_client`` back-door is closed (D-06).

    Today (Wave 0) ``search_flights`` is a ``StructuredTool`` wrapper from
    LangChain's ``@tool`` decorator and naturally has no ``_flight_client``
    attribute except in the running app where ``api.main.lifespan`` sets it.
    After Wave 1, ``search_flights`` is a plain async function and no caller
    sets the attribute — the test continues to pass for the right reason.
    """
    assert not hasattr(search_flights, "_flight_client")


def test_search_flights_first_param_is_runcontext() -> None:
    """The first positional parameter is ``ctx: RunContext[ChatDeps]``.

    The annotation is matched by string membership rather than by importing
    ``RunContext`` directly: a plain string check stays robust to the user
    writing the annotation as either ``RunContext[ChatDeps]`` (explicit
    import) or ``"RunContext[ChatDeps]"`` (deferred string-form), and avoids
    coupling this anti-pattern lock to PydanticAI's exact import path.

    Today (Wave 0) the function is wrapped in ``StructuredTool`` and
    ``inspect.signature`` raises — the assertion fails RED with a clear
    "TypeError" message. After Wave 1 (plain async def) it passes.
    """
    sig = inspect.signature(search_flights)
    first_param = next(iter(sig.parameters.values()))
    assert first_param.name == "ctx"
    annotation_str = str(first_param.annotation)
    assert "RunContext" in annotation_str, (
        f"first param annotation must reference RunContext; got {annotation_str!r}"
    )
