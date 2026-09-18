#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Postgres:"
docker compose ps postgres

echo "API:"
curl -fsS http://localhost:8000/health || true

echo

echo "Ollama:"
curl -fsS http://localhost:11434/api/tags >/dev/null && echo "Ollama reachable" || echo "Ollama not reachable"
