#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://localhost:8000}"
echo "API:"; curl -fsS "$BASE/health" && echo
echo "Status:"; curl -fsS "$BASE/v1/system/status" | head -c 400; echo
