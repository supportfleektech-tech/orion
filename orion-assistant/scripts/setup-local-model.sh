#!/usr/bin/env bash
# Install Ollama and pull the best local model this machine can actually run.
#
#   ./scripts/setup-local-model.sh            # auto-detect the right tier
#   ./scripts/setup-local-model.sh qwen3.5:4b # force a specific model
#
# Requires outbound access to ollama.com. If your network blocks it, see
# docs/LOCAL_MODELS.md for the airgapped GGUF path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
warn() { printf "\033[33m%s\033[0m\n" "$1"; }
fail() { printf "\033[31m%s\033[0m\n" "$1" >&2; exit 1; }

# ---------------------------------------------------------------- hardware
RAM_GB=$(awk '/MemTotal/ {printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null \
  || (sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.1f", $1/1024/1024/1024}') \
  || echo "8.0")
DISK_GB=$(df -Pk . | awk 'NR==2 {printf "%.1f", $4/1024/1024}')

bold "== Hardware"
echo "   RAM:  ${RAM_GB} GB"
echo "   Disk: ${DISK_GB} GB free"

pick_model() {
  awk -v r="$RAM_GB" 'BEGIN {
    if (r >= 14)      print "qwen3.5:9b 6.6"
    else if (r >= 12) print "qwen3-vl:8b 5.8"
    else if (r >= 7)  print "qwen3.5:4b 3.4"
    else if (r >= 5)  print "gemma3:4b 3.3"
    else              print "qwen3:1.7b 1.4"
  }'
}

if [ $# -ge 1 ]; then
  MODEL="$1"; SIZE="?"
else
  read -r MODEL SIZE <<<"$(pick_model)"
fi

EMBED="nomic-embed-text"
bold "== Selected model"
echo "   $MODEL  (~${SIZE} GB)  + $EMBED (~0.3 GB)"
if [ "$SIZE" != "?" ] && awk "BEGIN{exit !($DISK_GB < $SIZE + 1)}"; then
  fail "Not enough free disk: need ~$(awk "BEGIN{print $SIZE+1}") GB, have ${DISK_GB} GB"
fi

# ---------------------------------------------------------------- install
if ! command -v ollama >/dev/null 2>&1; then
  bold "== Installing Ollama"
  if ! curl -fsSL --connect-timeout 15 https://ollama.com/install.sh -o /tmp/ollama-install.sh; then
    fail "Cannot reach ollama.com. Your network may block it -- see docs/LOCAL_MODELS.md."
  fi
  sh /tmp/ollama-install.sh
else
  echo "   Ollama already installed: $(ollama --version 2>/dev/null || echo present)"
fi

# ---------------------------------------------------------------- serve
if ! curl -fsS --connect-timeout 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  bold "== Starting Ollama"
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS --connect-timeout 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
    || fail "Ollama did not start; see /tmp/ollama.log"
fi
echo "   Ollama is serving on http://127.0.0.1:11434"

# ---------------------------------------------------------------- pull
bold "== Pulling models (this can take a while)"
ollama pull "$MODEL"
ollama pull "$EMBED"

# ---------------------------------------------------------------- wire up
if [ -f .env ]; then
  bold "== Updating .env"
  tmp=$(mktemp)
  grep -v -E '^(OLLAMA_MODEL|OLLAMA_EMBED_MODEL|OLLAMA_BASE_URL)=' .env > "$tmp" || true
  {
    echo "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1"
    echo "OLLAMA_MODEL=$MODEL"
    echo "OLLAMA_EMBED_MODEL=$EMBED"
  } >> "$tmp"
  mv "$tmp" .env
  echo "   Set OLLAMA_MODEL=$MODEL"
else
  warn "   No .env found -- copy .env.example first, then set OLLAMA_MODEL=$MODEL"
fi

bold "== Done"
echo "   Restart ORION:  ./scripts/dev.sh"
echo "   Verify:         curl -s localhost:8000/v1/models/status | head -40"
