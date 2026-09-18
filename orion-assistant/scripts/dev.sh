#!/usr/bin/env bash
# Start backend + frontend for local development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT

(cd backend && PYTHONPATH=. DATABASE_URL="${DATABASE_URL:-sqlite:///../orion.db}" KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-../knowledge}" \
  ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload) &
(cd frontend && npm run dev) &
wait
