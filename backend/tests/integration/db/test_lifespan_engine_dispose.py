"""Integration test: lifespan ``await engine.dispose()`` runs on shutdown.

Plan 06-04 truth #6 + threat T-06-04-02: the FastAPI lifespan disposes the
async engine on shutdown so pooled connections close cleanly between
hot-reloads. We drive the lifespan around an asserted teardown via
:class:`httpx.AsyncClient` + :class:`httpx.ASGITransport` (the transport
runs Starlette's native lifespan_context automatically on enter / exit).

We instrument :meth:`engine.dispose` with a MagicMock wrapper so the test
asserts the dispose call happened (which is the testable wire-level
contract); SQLAlchemy 2.0's behaviour after ``dispose()`` is
implementation-defined enough that asserting "engine raises on connect"
is brittle (a fresh pool could be lazily re-created). Instrumenting the
call is the deterministic shape.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(database_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(  # noqa: S603 — trusted args, no shell
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def reloaded_app(
    pg_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[FastAPI, AsyncMock]]:
    """Reload the app modules against the per-test database and stub engine.dispose.

    Returns ``(app, dispose_spy)`` where ``dispose_spy`` is the AsyncMock
    that captures the lifespan's ``await engine.dispose()`` call. Wiring the
    spy onto a freshly-reloaded ``app.db.session.engine`` keeps the test
    isolated from the module-level singleton other tests might mutate.
    """
    monkeypatch.setenv("DATABASE_URL", pg_database_url)
    _run_alembic_upgrade(pg_database_url)

    import importlib  # noqa: PLC0415

    import app.api.main  # noqa: PLC0415
    import app.config  # noqa: PLC0415
    import app.db.session  # noqa: PLC0415

    importlib.reload(app.config)
    importlib.reload(app.db.session)
    importlib.reload(app.api.main)

    # Wrap the freshly-loaded engine in a thin proxy whose ``dispose`` is the
    # AsyncMock spy; every other attribute delegates to the real engine. The
    # lifespan imports ``engine`` directly into ``app.api.main`` — pointing
    # that module attribute at the proxy is enough to capture the call without
    # touching ``AsyncEngine`` itself, which has read-only attributes that
    # block direct ``setattr`` even via ``object.__setattr__``.
    real_engine = app.db.session.engine
    dispose_spy = AsyncMock(side_effect=real_engine.dispose)

    class _EngineProxy:
        def __init__(self, target: object, dispose: AsyncMock) -> None:
            self._target = target
            self.dispose = dispose

        def __getattr__(self, name: str) -> object:
            return getattr(self._target, name)

    proxy = _EngineProxy(real_engine, dispose_spy)
    monkeypatch.setattr(app.api.main, "engine", proxy)

    yield app.api.main.app, dispose_spy


async def test_lifespan_dispose_closes_engine_on_shutdown(
    reloaded_app: tuple[FastAPI, AsyncMock],
) -> None:
    """The lifespan ``await engine.dispose()`` step actually runs on shutdown.

    httpx 0.28's ``ASGITransport`` does NOT run lifespan automatically — we
    drive the lifespan_context manager directly so the ``yield``/teardown
    boundary is the testable wire-level shape, independent of HTTP transport.
    """
    app, dispose_spy = reloaded_app

    async with app.router.lifespan_context(app):
        # Startup phase complete — ``await engine.dispose()`` has NOT run yet.
        assert dispose_spy.await_count == 0
        # The DB engine is stashed on app.state per the new lifespan.
        assert app.state.db_engine is not None

    # Lifespan exit drives the shutdown; ``await engine.dispose()``
    # is the new step the plan is locking. The spy proves it ran exactly once.
    assert dispose_spy.await_count == 1
