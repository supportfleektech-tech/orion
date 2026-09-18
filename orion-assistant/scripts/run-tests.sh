#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
echo "==> Backend tests"
(cd backend && ../.venv/bin/python -m pytest -q)
echo "==> Frontend typecheck + build"
(cd frontend && npm run build)
