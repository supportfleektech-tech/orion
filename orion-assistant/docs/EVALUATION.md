# Evaluation

## Automated tests

```bash
./scripts/run-tests.sh
```

69 backend tests covering:

* **API integration** — health, status, tools, chat, conversations, memory, knowledge, settings,
  kill switch, automations, metrics, audit, and the full approval flow (request → approve → execute)
* **Retrieval** — hashed embedding determinism and discrimination, hybrid search relevance,
  memory upsert-by-key semantics
* **Ingestion** — chunking with overlap, empty input, format support, unsupported-type rejection
* **Tools and policy** — arithmetic allowlist, injection rejection, exponent bounds, registry
  schema generation, risk-tier approval requirement, kill-switch enforcement, and the guarantee that
  optional dependencies (playwright, mcp) are never imported at boot
* **Agent loop** — the real tool-calling cycle against a mock OpenAI-compatible server:
  plain answers, single and multi-step tool chains, parallel tool calls in one turn, bounded
  iteration, failing and unknown tools, malformed arguments, approval gating mid-loop, kill-switch
  enforcement, provider failure falling back to degraded, trace persistence, and history replay
* **Streaming** — SSE event sequence and ordering (`tool_start` before `tool_result` before
  `message`), conversation persistence, run recording, and tool failures surfaced mid-stream
* **Auth** — token required/rejected/accepted, malformed headers, protection of destructive
  endpoints, and reads staying public
* **Configuration** — runtime setting overrides persist across restarts; secrets are not mutable
* **Prompt** — the system prompt loads from `app/prompts/system.md` and covers injection and secrets

Frontend quality is enforced by a strict TypeScript build (`noUnusedLocals`,
`noUnusedParameters`) and lint by `ruff` on the backend. CI runs all of it plus both Docker builds.

## Manual acceptance checklist

1. Command Center shows provider state and live counters.
2. Chat persists across reloads; conversation list loads history.
3. With no model running, chat returns a labelled retrieval-only answer rather than an error.
4. Uploading a document indexes it and it becomes searchable.
5. A memory stored in the UI is retrieved in a later conversation.
6. Running `write_file` from the Tools page creates an approval; approving executes it.
7. The kill switch blocks all tools and the Topbar shows the alert state.
8. An automation runs on demand and records its result.
9. Observability shows the run with a complete trace.
10. Toggling a flag in Settings changes tool availability immediately.

## Regression philosophy

Because model output is non-deterministic, tests assert on *contracts* — status codes, persistence,
policy decisions, retrieval ranking — not on generated prose. The degraded path is deliberately
tested, since it is the only fully deterministic generation mode.
