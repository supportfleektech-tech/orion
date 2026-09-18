#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

echo "==> Backend tests"
(cd backend && ../.venv/bin/python -m pytest -q)

echo "==> Backend lint"
(cd backend && ../.venv/bin/ruff check app tests)

echo "==> Frontend typecheck"
(cd frontend && npx tsc --noEmit)

echo "==> Frontend tests"
(cd frontend && npm test)

echo "==> Frontend build"
(cd frontend && npm run build)

echo "All green."
