"""Idempotent dev/test user seed (Phase 6 — REQ-p5-db-seed).

Reads ``seed.toml``, hashes each password with the project's pwdlib argon2
singleton (the SAME constructor used by ``app.auth.repository`` so seeded
hashes verify cleanly through ``PostgresUserRepository.verify_password``),
and upserts every user via ``INSERT ... ON CONFLICT (username) DO UPDATE``.
Re-running yields the same row count and refreshes hashes/disabled flags —
the seed is safe to run before every dev session.

Aborts with returncode ``2`` when ``settings.database_url`` host is not
``localhost``/``127.0.0.1``/``::1`` and ``settings.seed_allow_non_local`` is
``False`` — defends against accidental invocation against a remote DB
(threat T-06-06-02 / RESEARCH §Anti-Pattern "seed.toml content as a
security boundary").

Run via the ``just db-seed`` recipe (which `cd`'s into ``backend/``):

    cd backend && uv run python scripts/seed.py [seed.toml]

Returncodes:
    ``0`` — seed completed (or no users to seed; idempotent no-op).
    ``1`` — TOML file not found at the resolved path.
    ``2`` — non-local database_url with ``seed_allow_non_local`` False.
"""

from __future__ import annotations

import asyncio
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

# When invoked directly via ``python scripts/seed.py`` (the ``just db-seed``
# path), Python adds ``scripts/`` to ``sys.path`` but not the ``backend/``
# package root, so ``from app...`` imports fail. Prepend the parent
# directory so the script and the test importer agree on the module layout.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402 — sys.path tweak above must precede app imports
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.auth.repository import _password_hasher  # noqa: E402
from app.config import settings  # noqa: E402

# Hosts treated as "local" for the non-local-DB guard. This is a contract
# (which hostnames count as localhost), not a tunable knob, so it lives as a
# module constant per CLAUDE.md.
_LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

# Bound-parameter SQL — defence against SQL injection (threat T-06-06-02).
# ON CONFLICT (username) DO UPDATE refreshes hashed_password + disabled in
# place; rows are never duplicated, every re-run produces a freshly-salted
# argon2 hash so the test in test_seed_idempotent.py can assert that the
# stored hash changes between runs while still verifying the same password.
# ``id`` is set Python-side via uuid4(); the User SQLModel uses
# ``default_factory=uuid4`` rather than a server-side default, so the column
# has no DB default and a raw INSERT must supply it. ON CONFLICT (username)
# means the freshly-generated id is discarded for existing rows — only the
# hashed_password + disabled fields update.
_UPSERT_SQL = text(
    """
    INSERT INTO "user" (id, username, hashed_password, disabled)
    VALUES (:id, :u, :h, :d)
    ON CONFLICT (username) DO UPDATE
      SET hashed_password = EXCLUDED.hashed_password,
          disabled = EXCLUDED.disabled
    """,
)


def _is_local(database_url: str) -> bool:
    """Return True when *database_url* points at a localhost-equivalent host.

    A ``None`` hostname (rare but possible for malformed URLs) is treated as
    non-local conservatively — better to abort with an unhelpful URL than
    seed against the wrong target.
    """
    parsed = urlparse(database_url)
    return parsed.hostname in _LOCAL_HOSTS


def _resolve_seed_path(argv: list[str]) -> Path:
    """Resolve the seed-file path from CLI args, defaulting to ``seed.toml``.

    The default is relative to the current working directory; ``just db-seed``
    invokes the script with ``cwd=backend/`` so ``seed.toml`` resolves to
    ``backend/seed.toml`` without further wiring.
    """
    return Path(argv[1]) if len(argv) > 1 else Path("seed.toml")


async def seed(toml_path: Path) -> int:
    """Upsert users from *toml_path* into the ``user`` table.

    Args:
        toml_path: Filesystem path to the TOML file containing ``[[users]]``
            blocks (each with ``username``, ``password``, ``disabled``).

    Returns:
        ``0`` on success (including the empty-users no-op case),
        ``1`` if *toml_path* does not exist,
        ``2`` if the configured database_url is non-local without override.
    """
    if not toml_path.exists():
        print(f"seed file not found: {toml_path}", file=sys.stderr)
        return 1

    data = tomllib.loads(toml_path.read_text())
    users = data.get("users", [])
    if not users:
        # Empty TOML is a no-op (idempotent — running against an empty seed
        # file should not abort the broader bootstrap pipeline).
        print("no users to seed")
        return 0

    if not _is_local(settings.database_url) and not settings.seed_allow_non_local:
        print(
            "refusing to seed against non-local database_url; set SEED_ALLOW_NON_LOCAL=true to override",
            file=sys.stderr,
        )
        return 2

    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            for entry in users:
                params = {
                    "id": uuid4(),
                    "u": entry["username"],
                    "h": _password_hasher.hash(entry["password"]),
                    "d": bool(entry.get("disabled", False)),
                }
                await conn.execute(_UPSERT_SQL, params)
            await conn.commit()
    finally:
        await engine.dispose()

    print(f"seeded {len(users)} user(s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(seed(_resolve_seed_path(sys.argv))))
