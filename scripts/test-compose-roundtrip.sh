#!/usr/bin/env bash
# Phase 6 — REQ-postgres-redis-compose acceptance: data persists across compose
# restart. Exit 0 on success, non-zero on any step failure.
#
# Usage: bash scripts/test-compose-roundtrip.sh
#
# Locks ROADMAP success criterion #1 — "data survives docker compose down && up".
# Run from the repo root; the script does NOT clean up afterward (developers
# expect their `pgdata` to survive). For destructive cleanup, use
# `just compose-down-clean`.

set -euo pipefail

# --- Step 1: docker daemon must be running --------------------------------
if ! docker info > /dev/null 2>&1; then
  echo "Docker daemon not running" >&2
  exit 1
fi

# --- Step 2: bring the db service up; wait for healthcheck ----------------
docker compose up -d --wait

# --- Step 3: apply the Phase 6 schema -------------------------------------
(cd backend && uv run alembic upgrade head)

# --- Step 4: ensure seed.toml exists; run the idempotent seed --------------
[ -f backend/seed.toml ] || cp backend/seed.toml.example backend/seed.toml
(cd backend && uv run python scripts/seed.py)

# --- Step 5: capture the user count before restart ------------------------
BEFORE=$(docker compose exec -T db psql -U trip_planner -d trip_planner -tAc 'SELECT count(*) FROM "user"')
if [ "$BEFORE" -le 0 ]; then
  echo "no users seeded" >&2
  exit 2
fi

# --- Step 6: take the stack down (preserves the pgdata volume) ------------
docker compose down

# --- Step 7: bring it back up ---------------------------------------------
docker compose up -d --wait

# --- Step 8: count must match — that is the assertion target --------------
AFTER=$(docker compose exec -T db psql -U trip_planner -d trip_planner -tAc 'SELECT count(*) FROM "user"')
if [ "$BEFORE" != "$AFTER" ]; then
  echo "data did not persist: before=$BEFORE after=$AFTER" >&2
  exit 3
fi

# --- Step 9: report success -----------------------------------------------
echo "compose round-trip OK: $AFTER users persisted across restart"
exit 0
