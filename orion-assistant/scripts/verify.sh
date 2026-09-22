#!/usr/bin/env bash
#
# One command to prove ORION works on this machine, end to end, with a real
# model. Everything else in CI runs against a mock LLM because CI has no GPU
# and often no network; this is the check that closes that gap.
#
#   ./scripts/verify.sh
#
# It will, in order:
#   1. create the Python venv and install dependencies
#   2. install Ollama and pull a model sized for this machine (unless present)
#   3. run the offline test suite
#   4. start the backend
#   5. run the real-model acceptance checks against it
#   6. stop the backend again
#
# Safe to re-run. Anything already done is skipped.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
die()  { printf "\033[31m✗ %s\033[0m\n" "$1" >&2; exit 1; }

API_PID=""
cleanup() {
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ------------------------------------------------------------ 1. toolchain
bold "== 1/5  Dependencies"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || die "could not create .venv (is python3-venv installed?)"
  ok "created .venv"
fi
.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1
.venv/bin/pip install -q -r backend/requirements-dev.txt || die "dependency install failed"
ok "backend dependencies"

if [ -d frontend ] && command -v npm >/dev/null 2>&1; then
  if [ ! -d frontend/node_modules ]; then
    (cd frontend && npm ci --no-audit --no-fund >/dev/null 2>&1) && ok "frontend dependencies" \
      || warn "frontend install failed (backend checks will still run)"
  else
    ok "frontend dependencies"
  fi
fi

# --------------------------------------------------------------- 2. model
bold "== 2/5  Local model"
if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama is not installed — running ./scripts/setup-local-model.sh"
  ./scripts/setup-local-model.sh || die "model setup failed; see docs/LOCAL_MODELS.md"
elif ! curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  warn "Ollama is installed but not running — starting it"
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi

MODELS="$(curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags 2>/dev/null \
  | python3 -c 'import sys,json;print(" ".join(m["name"] for m in json.load(sys.stdin).get("models",[])))' 2>/dev/null)"
if [ -z "${MODELS// }" ]; then
  warn "no models pulled yet — running ./scripts/setup-local-model.sh"
  ./scripts/setup-local-model.sh || die "could not pull a model; see docs/LOCAL_MODELS.md"
  MODELS="$(curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags 2>/dev/null \
    | python3 -c 'import sys,json;print(" ".join(m["name"] for m in json.load(sys.stdin).get("models",[])))' 2>/dev/null)"
fi
[ -n "${MODELS// }" ] || die "no local model available"
ok "models: $MODELS"

# Prefer the configured model (including the project .env) rather than an
# arbitrary first entry from Ollama's list. The list order is not a capability
# ranking, and a text-only or weak tool-calling model can make the real-model
# acceptance checks fail even when a suitable model is already installed.
CONFIGURED_MODEL="${OLLAMA_MODEL:-}"
if [ -z "$CONFIGURED_MODEL" ] && [ -f .env ]; then
  CONFIGURED_MODEL="$(sed -n 's/^OLLAMA_MODEL=//p' .env | tail -n 1)"
  CONFIGURED_MODEL="${CONFIGURED_MODEL#\"}"
  CONFIGURED_MODEL="${CONFIGURED_MODEL%\"}"
fi

if [ -n "$CONFIGURED_MODEL" ]; then
  MODEL="$CONFIGURED_MODEL"
elif printf '%s' "$MODELS" | tr ' ' '\n' | grep -qx 'qwen3.5:9b'; then
  MODEL="qwen3.5:9b"
elif printf '%s' "$MODELS" | tr ' ' '\n' | grep -qx 'qwen3.5:4b'; then
  MODEL="qwen3.5:4b"
elif printf '%s' "$MODELS" | tr ' ' '\n' | grep -qx 'qwen3:1.7b'; then
  MODEL="qwen3:1.7b"
else
  MODEL="$(printf '%s' "$MODELS" | awk '{print $1}')"
fi
ok "using: $MODEL"

# -------------------------------------------------------------- 3. offline
bold "== 3/5  Offline test suite"
./scripts/run-tests.sh >/tmp/orion-tests.log 2>&1 \
  && ok "all tests pass" \
  || die "tests failed — see /tmp/orion-tests.log"

# -------------------------------------------------------------- 4. backend
bold "== 4/5  Backend"
export OLLAMA_MODEL="$MODEL"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/orion.db}"
export KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-$ROOT/knowledge}"
mkdir -p "$KNOWLEDGE_DIR"

(cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  >/tmp/orion-api.log 2>&1) &
API_PID=$!

for _ in $(seq 1 40); do
  curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1 \
  || die "backend did not start — see /tmp/orion-api.log"
ok "listening on :8000"

# ---------------------------------------------------------- 5. real model
bold "== 5/5  Real-model acceptance"
echo
./scripts/verify-real-model.sh
RESULT=$?

echo
if [ $RESULT -eq 0 ]; then
  bold "ORION is verified against a real model on this machine."
else
  bold "Some checks failed — see the output above."
  echo "Capability gaps on a small model are expected; safety failures are not."
fi
exit $RESULT
