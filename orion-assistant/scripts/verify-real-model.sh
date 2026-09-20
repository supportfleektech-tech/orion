#!/usr/bin/env bash
#
# Acceptance check against a REAL local model.
#
# Everything in CI runs against a mock LLM, because CI has no GPU and often no
# network. That leaves one surface untested: whether a genuine model actually
# drives the tool loop, streams tokens, and grounds answers in retrieval.
# This script is that test. Run it once on a machine with Ollama.
#
#   ./scripts/run-backend.sh          # in one terminal
#   ./scripts/verify-real-model.sh    # in another
#
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
API="${ORION_API:-http://127.0.0.1:8000}"

pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n'  "$1"; fail=$((fail+1)); }
note() { printf '        %s\n' "$1"; }

jqf() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }

echo "==> ORION real-model acceptance  ($API)"
echo

# ---------------------------------------------------------------- reachable
status="$(curl -s --max-time 10 "$API/v1/system/status")" || true
if [ -z "$status" ]; then
  echo "Cannot reach $API. Start the backend first: ./scripts/run-backend.sh"
  exit 1
fi

model="$(printf '%s' "$status" | jqf "d['providers']['local']['model']")"
reachable="$(printf '%s' "$status" | jqf "d['providers']['local']['reachable']")"

echo "Local model: ${model:-unknown}   reachable: ${reachable:-?}"
echo

# The bundled demo model answers by pattern-matching, so it would fail the
# comprehension checks below for reasons that say nothing about ORION.
if [ "${model:-}" = "orion-demo" ]; then
  echo "This is the bundled demo model, not a real one. It pattern-matches"
  echo "fixed phrasings, so the reasoning checks below would fail regardless"
  echo "of whether ORION works. Point OLLAMA_MODEL at a real model first."
  exit 1
fi

if [ "$reachable" != "True" ]; then
  echo "No local model is reachable, so this script would only be testing the"
  echo "degraded path -- which CI already covers. Start Ollama and pull a model:"
  echo "    ./scripts/setup-local-model.sh"
  exit 1
fi

# ------------------------------------------------------------------- 1. chat
echo "[1/6] A plain question gets a real answer"
body="$(curl -s --max-time 180 -X POST "$API/v1/chat" \
  -H 'content-type: application/json' \
  -d '{"message":"In one short sentence, what is the capital of France?"}')"
answer="$(printf '%s' "$body" | jqf "d.get('result','')")"
degraded="$(printf '%s' "$body" | jqf "d.get('degraded')")"

if [ "$degraded" = "True" ]; then
  bad "the run fell back to degraded mode"
elif printf '%s' "$answer" | grep -qi "paris"; then
  ok "answered correctly"
else
  bad "unexpected answer: ${answer:0:120}"
fi

# ------------------------------------------------------------- 2. tool loop
echo "[2/6] A calculation actually calls the calculator"
body="$(curl -s --max-time 180 -X POST "$API/v1/chat" \
  -H 'content-type: application/json' \
  -d '{"message":"Use your calculator tool: what is 1287 multiplied by 43?"}')"
tools="$(printf '%s' "$body" | jqf "[s.get('tool') for s in d.get('trace',[]) if isinstance(s,dict) and s.get('tool')]")"
answer="$(printf '%s' "$body" | jqf "d.get('result','')")"

printf '%s' "$tools" | grep -q "calculate" \
  && ok "the model chose the calculate tool" \
  || bad "no calculate call in the trace: $tools"

printf '%s' "$answer" | grep -q "55341" \
  && ok "arithmetic is correct (55341)" \
  || bad "wrong or missing result: ${answer:0:120}"

# -------------------------------------------------------------- 3. streaming
echo "[3/6] Tokens stream incrementally rather than arriving in one lump"
stream="$(curl -s --max-time 180 -N -X POST "$API/v1/chat/stream" \
  -H 'content-type: application/json' \
  -d '{"message":"Count from one to five, in words."}')"
tokens="$(printf '%s' "$stream" | grep -c '^event: token')"

[ "$tokens" -gt 3 ] \
  && ok "$tokens token events" \
  || bad "only $tokens token events -- streaming may be falling back to buffered"

printf '%s' "$stream" | grep -q '^event: done' \
  && ok "stream terminated cleanly" \
  || bad "no done event"

# --------------------------------------------------------------- 4. grounding
echo "[4/6] Retrieval grounds the answer"
curl -s --max-time 60 -X POST "$API/v1/knowledge/ingest-text" \
  -H 'content-type: application/json' \
  -d '{"name":"orion-fact.md","content":"The ORION project codename for the 2026 release is Halcyon Drift."}' >/dev/null

body="$(curl -s --max-time 180 -X POST "$API/v1/chat" \
  -H 'content-type: application/json' \
  -d '{"message":"What is the ORION project codename for the 2026 release?"}')"
answer="$(printf '%s' "$body" | jqf "d.get('result','')")"

printf '%s' "$answer" | grep -qi "halcyon" \
  && ok "recalled a fact that only exists in the knowledge base" \
  || bad "did not ground the answer: ${answer:0:140}"

# ---------------------------------------------------------------- 5. memory
echo "[5/6] Memory survives across conversations"
curl -s --max-time 60 -X POST "$API/v1/memory" \
  -H 'content-type: application/json' \
  -d '{"kind":"preference","content":"The user prefers answers in metric units.","key":"units"}' >/dev/null

body="$(curl -s --max-time 180 -X POST "$API/v1/chat" \
  -H 'content-type: application/json' \
  -d '{"message":"What unit preference do you remember about me?"}')"
answer="$(printf '%s' "$body" | jqf "d.get('result','')")"

printf '%s' "$answer" | grep -qi "metric" \
  && ok "recalled the stored preference" \
  || bad "did not recall it: ${answer:0:140}"

# ------------------------------------------------------------ 6. evaluations
echo "[6/6] The shipped evaluation suites run against this model"
for suite in core safety; do
  result="$(curl -s --max-time 900 -X POST "$API/v1/evaluations/$suite/run")"
  total="$(printf '%s' "$result" | jqf "d.get('total',0)")"
  passed="$(printf '%s' "$result" | jqf "d.get('passed',0)")"

  if [ -z "$total" ] || [ "$total" = "0" ]; then
    bad "$suite did not run"
    continue
  fi

  if [ "$suite" = "safety" ] && [ "$passed" != "$total" ]; then
    bad "safety $passed/$total -- a guardrail failure is a policy bug, not a model limitation"
    printf '%s' "$result" | jqf "'        failed: ' + ', '.join(c['id'] for c in d['cases'] if not c['passed'])"
  else
    ok "$suite $passed/$total"
    [ "$passed" != "$total" ] && printf '%s' "$result" | \
      jqf "'        failed: ' + ', '.join(c['id'] for c in d['cases'] if not c['passed'])"
  fi
done

echo
echo "==> $pass passed, $fail failed"
[ "$fail" -eq 0 ] && echo "The real-model path works end to end." || \
  echo "Capability gaps in 'core' are expected on small models; safety failures are not."
exit $((fail > 0))
