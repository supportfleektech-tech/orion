# Agent Runtime

Implementation: `backend/app/services/agent_runtime.py`.

## Loop

```
build_context → model call → tool calls? → execute via policy gate → feed results back
                     ▲                                                      │
                     └──────────────────────────────────────────────────────┘
                     (max MAX_TOOL_LOOPS iterations)
```

1. **Context** — `retrieve_memories` and `search_chunks` produce a compact evidence block.
2. **Messages** — system prompt, context block, last `MAX_HISTORY_MESSAGES` turns, new user turn.
3. **Routing** — `estimate_complexity` (length + analytical markers) selects `normal` or `heavy`;
   heavy tasks prefer cloud when escalation is enabled and configured.
4. **Tools** — only policy-allowed tools are advertised. Each call is JSON-parsed defensively,
   executed through `execute_tool`, and its result is appended as a `tool` message.
5. **Termination** — the loop ends when the model returns no tool calls or the budget is exhausted.
6. **Persistence** — the run, full trace and a low-confidence interaction summary are stored.

## Degraded mode

If every provider fails and `OFFLINE_FALLBACK_ENABLED` is true, the router returns a labelled
offline response. The runtime then attempts `fallback.extractive_answer`, which ranks sentences from
retrieved memories and chunks by keyword overlap and returns the top five with source attribution.
The user always gets something grounded and clearly labelled rather than an error.

## Tool execution contract

`execute_tool` returns one of:

```json
{"ok": true, "result": {...}}
{"ok": false, "error": "reason"}
{"ok": false, "approval_required": true, "approval_id": "uuid", "error": "..."}
```

Every outcome is written to `tool_runs` and `audit_events`.

## System prompt

Stored as `SYSTEM_PROMPT` in the module. It establishes: concision, evidence orientation, treating
memory as context rather than truth, no fabricated action claims, approval for risky actions, no
secret or chain-of-thought disclosure, and stating assumptions when ambiguous.

## Tracing

Each iteration appends `{step, provider, model, latency_ms, text, tool_calls}` and each tool call
appends `{step, tool, arguments, result_ok}`. Traces are visible at `/v1/runs/{id}` and in the
Observability page.
