#!/usr/bin/env bash
set -euo pipefail
[ $# -eq 1 ] || { echo "Usage: $0 <path-or-file>"; exit 2; }
BASE="${ORION_API:-http://localhost:8000}"
curl -fsS -X POST "$BASE/v1/knowledge/ingest" -H 'content-type: application/json' \
  -d "{\"path\": \"$1\"}"
echo
