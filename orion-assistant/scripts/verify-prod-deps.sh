#!/usr/bin/env bash
# The app must boot with ONLY backend/requirements.txt installed.
# playwright and mcp are optional extras and must never be required at import time.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$(mktemp -d)/prodenv"

python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"

cd "$ROOT/backend"
PYTHONPATH=. DATABASE_URL="sqlite:///$(mktemp -d)/verify.db" "$VENV/bin/python" - <<'PY'
import sys
from app.main import app  # noqa: F401
from app.services.agent_runtime import SYSTEM_PROMPT

assert "playwright" not in sys.modules, "playwright must not be imported at boot"
assert "mcp" not in sys.modules, "mcp must not be imported at boot"
assert "ORION" in SYSTEM_PROMPT, "system prompt failed to load from app/prompts/system.md"
print("OK: production dependency set boots cleanly without optional extras")
PY
