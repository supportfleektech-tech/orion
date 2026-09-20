#!/usr/bin/env bash
# Database migrations.
#
#   ./scripts/migrate.sh            # apply pending migrations
#   ./scripts/migrate.sh status     # show current vs head revision
#   ./scripts/migrate.sh new "msg"  # autogenerate a revision from model changes
#   ./scripts/migrate.sh down       # roll back one revision
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
ALEMBIC=("$PY" -m alembic)

case "${1:-upgrade}" in
  upgrade|"") "${ALEMBIC[@]}" upgrade head ;;
  status)
    "${ALEMBIC[@]}" current
    echo "--- head:"
    "${ALEMBIC[@]}" heads
    ;;
  new)
    [ $# -ge 2 ] || { echo "usage: ./scripts/migrate.sh new \"description\"" >&2; exit 1; }
    "${ALEMBIC[@]}" revision --autogenerate -m "$2"
    echo "Review the generated file in backend/migrations/versions/ before committing."
    ;;
  down) "${ALEMBIC[@]}" downgrade -1 ;;
  *) echo "unknown command: $1" >&2; exit 1 ;;
esac
