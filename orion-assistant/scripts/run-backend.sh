#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT/backend"
PYTHONPATH=. DATABASE_URL="${DATABASE_URL:-sqlite:///../orion.db}" KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-../knowledge}" \
  ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
