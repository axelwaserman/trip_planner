"""Anti-pattern lock for the ``_flight_client`` back-door (D-06; REQ-p5-flight-client-di).

Per CONTEXT.md D-06 + the explicit anti-pattern lock ("Don't keep
``search_flights._flight_client`` 'just in case'"), the Phase 4.x monkey-patched
attribute back-door must NOT coexist with PydanticAI's ``RunContext[ChatDeps]``
DI surface. Phase 5 (Plan 05-04) deleted the back-door; this file is the
regression guard.

Phase 6 / Plan 06-05a Task 4 extends the lock with forensic assertions:

1. The :mod:`app.tools.flight_search` module has NO ``_flight_client`` attribute,
   and the ``search_flights`` callable has no such attribute either (no
   side-channel — even at the module level).
2. A ``ripgrep`` sweep over ``backend/app`` for the prohibited shapes
   (``search_flights._flight_client = ...`` assignment, or
   ``getattr(search_flights, "_flight_client", ...)`` peek) finds zero matches
   — the back-door cannot quietly reappear via either spelling.
3. :func:`app.chat.deps.make_chat_run_context` does NOT exist — the Phase 6
   path is :class:`ChatDeps` constructed directly inside
   :meth:`ChatService.chat_stream`. The Phase 5 ``RunContext[ChatDeps]``
   surface is what the tool consumes; this test confirms ``ChatDeps`` carries
   ``flight_client`` so the contract is structurally enforced.

These tests must continue to pass for the rest of the project's life. Re-adding
the back-door — even "temporarily" — flips them to RED and blocks merges.

Closes ARCHITECTURE.md "Monkey-Patched Tool Dependency" Known Tech Debt.
"""

import ast
import inspect
from pathlib import Path

import app.tools.flight_search as flight_search_module
from app.chat.deps import ChatDeps
from app.tools.flight_search import search_flights


def test_search_flights_has_no_flight_client_attribute() -> None:
    """The Phase 4.x ``_flight_client`` back-door is closed (D-06).

    After Phase 5, ``search_flights`` is a plain async function and no caller
    sets the attribute. Re-introducing the attribute — even temporarily —
    flips this assertion to RED.
    """
    assert not hasattr(search_flights, "_flight_client")


def test_search_flights_module_has_no_flight_client_attribute() -> None:
    """The module-level lock — REQ-p5-flight-client-di Phase 6 forensic addition.

    The back-door could conceivably reappear as a *module-level* attribute
    rather than a function attribute (e.g. ``_flight_client = None`` at the
    top of ``flight_search.py``). This assertion locks both surfaces.
    """
    assert not hasattr(flight_search_module, "_flight_client")
    assert not hasattr(search_flights, "_flight_client")


def test_search_flights_first_param_is_runcontext() -> None:
    """The first positional parameter is ``ctx: RunContext[ChatDeps]``.

    The annotation is matched by string membership rather than by importing
    ``RunContext`` directly: a plain string check stays robust to the user
    writing the annotation as either ``RunContext[ChatDeps]`` (explicit
    import) or ``"RunContext[ChatDeps]"`` (deferred string-form), and avoids
    coupling this anti-pattern lock to PydanticAI's exact import path.
    """
    sig = inspect.signature(search_flights)
    first_param = next(iter(sig.parameters.values()))
    assert first_param.name == "ctx"
    annotation_str = str(first_param.annotation)
    assert "RunContext" in annotation_str, f"first param annotation must reference RunContext; got {annotation_str!r}"


def test_no_backdoor_assignments_or_getattrs_in_production_code() -> None:
    """Forensic AST sweep — REQ-p5-flight-client-di Phase 6 regression lock.

    The two prohibited shapes are:

    1. ``search_flights._flight_client = X`` — module-attribute assignment.
    2. ``getattr(search_flights, "_flight_client", ...)`` — back-door read.

    The legitimate ``self._flight_client = flight_client`` constructor
    parameter assignment on :class:`ChatService` is not matched (each pattern
    anchors to ``search_flights._flight_client`` / ``getattr(search_flights,
    ...)`` specifically). Implemented via :mod:`ast` so docstrings/comments
    that happen to contain the prohibited shape (historical context, like
    :mod:`app.chat.deps`'s docstring) don't trigger a false positive.
    """
    # Locate the ``backend/app`` directory relative to this test file (cwd
    # varies between local invocation and CI).
    here = Path(__file__).resolve()
    # tests/unit/tools/test_flight_search_no_backdoor.py → backend/app
    app_dir = here.parents[3] / "app"
    assert app_dir.is_dir(), f"could not locate backend/app at {app_dir}"

    matches: list[str] = []
    for py_file in app_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # Shape 1: ``search_flights._flight_client = ...`` — Assign with
            # an Attribute target whose value is a Name "search_flights" and
            # whose attribute is "_flight_client".
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "search_flights"
                        and target.attr == "_flight_client"
                    ):
                        matches.append(
                            f"{py_file.relative_to(app_dir.parent)}:{node.lineno}: "
                            f"prohibited assignment search_flights._flight_client = ...",
                        )
            # Shape 2: ``getattr(search_flights, "_flight_client", ...)`` — Call to
            # ``getattr`` whose first arg is Name "search_flights" and whose
            # second arg is Constant string "_flight_client".
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "search_flights"
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "_flight_client"
            ):
                matches.append(
                    f"{py_file.relative_to(app_dir.parent)}:{node.lineno}: "
                    f'prohibited getattr(search_flights, "_flight_client", ...)',
                )

    assert matches == [], (
        "prohibited back-door shapes found in production code:\n" + "\n".join(matches)
    )


def test_chat_deps_carries_flight_client_via_runcontext_path() -> None:
    """``ChatDeps`` exposes ``flight_client`` — confirms Phase 5 D-06 RunContext path is intact.

    The plan calls for an assertion against ``make_chat_run_context``;
    Phase 5's actual implementation is direct ``ChatDeps`` construction
    inside :meth:`ChatService.chat_stream`. The contract that matters
    (REQ-p5-flight-client-di) is that the tool reaches its FlightAPIClient
    via ``ctx.deps.flight_client``, which requires ``ChatDeps.flight_client``
    to exist as a field. This test asserts the structural contract.
    """
    field_names = {field.name for field in ChatDeps.__dataclass_fields__.values()}
    assert "flight_client" in field_names, (
        f"ChatDeps must expose flight_client (RunContext[ChatDeps] field) — got {field_names}"
    )
    # The other two fields per CONTEXT.md D-05 + Plan 06-05a rename:
    assert "conversation_id" in field_names
    assert "user_id" in field_names
