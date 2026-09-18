#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example"; fi

echo "==> Starting Postgres + pgvector"
docker compose up -d postgres

echo "==> Backend Python environment"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

echo "==> Frontend dependencies"
cd frontend
npm install
cd "$ROOT"

echo "==> Optional local models"
echo "Install Ollama separately, then run:"
echo "  ollama pull qwen3:4b"
echo "  ollama pull nomic-embed-text"

echo "Bootstrap complete."
