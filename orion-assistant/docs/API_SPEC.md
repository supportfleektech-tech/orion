# API Specification

Base URL: `http://localhost:8000` (or `/` through the nginx/Vite proxy).
Interactive docs: `/docs` · OpenAPI: `/openapi.json`

When `AUTH_ENABLED=true`, mutating endpoints require `Authorization: Bearer <ADMIN_TOKEN>`.

## System

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness, version, uptime |
| GET | `/v1/system/status` | Providers, counts, flags, tools, kill switch |
| GET | `/v1/system/metrics` | Success rates, latency, router stats, timeline |

## Chat

`POST /v1/chat`

```json
{ "message": "Summarize my project notes", "conversation_id": null, "mode": "auto" }
```

`mode` is `auto` | `local` | `cloud`. Response:

```json
{
  "conversation_id": "uuid", "run_id": "uuid",
  "result": "…", "provider": "local", "model": "qwen3:4b",
  "degraded": false, "duration_ms": 1840,
  "trace": [], "memories": [], "knowledge": []
}
```

`POST /v1/chat/stream` returns SSE events: `start`, `status`, `context`, `trace`, `message`, `done`.

`POST /v1/chat/stream` emits these SSE events in order:

| Event | Payload |
|---|---|
| `start` | `{conversation_id}` |
| `status` | `{stage, step?}` — `retrieving_context`, `reasoning` |
| `context` | `{memories, knowledge}` |
| `trace` | per-iteration `{step, provider, model, latency_ms, text, tool_calls}` |
| `tool_start` | `{step, tool, arguments}` — emitted *before* execution |
| `tool_result` | `{step, tool, result_ok, error?}` |
| `message` | `{role, content}` — the final answer |
| `done` | `{run_id, provider, model, degraded, duration_ms}` |
| `error` | `{message}` — only on failure |

Also: `GET /v1/conversations` (`?include_archived=`), `GET /v1/conversations/{id}`,
`DELETE /v1/conversations/{id}`, and:

`PATCH /v1/conversations/{id}` — `{title?, pinned?, archived?}`. Pinned conversations sort first;
archived ones are hidden from the default list.

## Memory

| Method | Path | Body / Query |
|---|---|---|
| POST | `/v1/memory` | `{content, kind, key?, confidence}` — upserts when `key` is given |
| GET | `/v1/memory` | `?kind=&limit=&offset=` |
| GET | `/v1/memory/search` | `?q=&limit=` |
| POST | `/v1/memory/{id}/pin` | `?pinned=true` |
| DELETE | `/v1/memory/{id}` | |

## Knowledge

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/knowledge/upload` | multipart `file` |
| POST | `/v1/knowledge/ingest` | `{path}` — file or directory inside `KNOWLEDGE_DIR` |
| POST | `/v1/knowledge/ingest-text` | `{name, content}` |
| GET | `/v1/knowledge/search` | `?q=&limit=` |
| GET | `/v1/knowledge/documents` | |
| DELETE | `/v1/knowledge/documents/{id}` | |

Re-ingesting identical content is a no-op (`status: unchanged`); changed content replaces the
previous version of that path.

## Tools

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/tools` | Schema, risk, category, allowed, policy reason |
| POST | `/v1/tools/run` | `{name, arguments, auto_approve?}` |
| POST | `/v1/tools/{name}/toggle` | `{enabled}` |
| GET | `/v1/tools/runs` | Execution history |

High-risk tools return `{"ok": false, "approval_required": true, "approval_id": "…"}`.

## Security & governance

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/approvals` | `?status_filter=pending\|all\|approved\|rejected` |
| POST | `/v1/approvals/{id}` | `{approve, execute}` |
| GET/POST | `/v1/security/kill-switch` | `{enabled, reason}` |
| GET | `/v1/audit` | Governed event log |

## Automations

`GET/POST /v1/automations`, `POST /v1/automations/{id}/run`, `DELETE /v1/automations/{id}`.
Body: `{name, prompt, schedule_seconds, enabled}`.

## Observability & settings

`GET /v1/runs`, `GET /v1/runs/{id}` (full trace), `GET /v1/settings`, `PATCH /v1/settings`.

## Errors

Standard FastAPI `{"detail": "..."}`. `400` invalid input, `401/403` auth, `404` missing,
`409` already resolved, `429` rate limited, `500` unexpected (logged, never leaks internals).
