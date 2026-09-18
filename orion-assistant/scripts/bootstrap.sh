#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

[ -f .env ] || { cp .env.example .env; echo "Created .env"; }

echo "==> Python environment"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -q -r backend/requirements-dev.txt

echo "==> Frontend dependencies"
(cd frontend && npm install --no-audit --no-fund)

mkdir -p knowledge
echo "==> Done. Run ./scripts/dev.sh to start everything."
