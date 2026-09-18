# API Specification

Base URL: `http://localhost:8000`

## Health

`GET /health`

Returns runtime health.

## Chat

`POST /v1/chat`

```json
{
  "message": "Summarize the latest project decisions in my knowledge base",
  "conversation_id": "optional-uuid",
  "mode": "auto"
}
```

Response:

```json
{
  "conversation_id": "uuid",
  "result": "...",
  "provider": "local",
  "model": "qwen3:4b",
  "trace": [],
  "memories": []
}
```

## Memory

`POST /v1/memory`

```json
{
  "content": "Project Orion uses PostgreSQL as its source of truth.",
  "kind": "project_fact",
  "key": "storage.primary",
  "confidence": 0.95
}
```

`GET /v1/memory/search?q=postgresql`

## Knowledge ingestion

`POST /v1/knowledge/ingest`

```json
{ "path": "knowledge/project-plan.md" }
```

The path is resolved on the server. Production deployment should use a configured allowlist rather than arbitrary filesystem access.

## Tools

`GET /v1/tools`

Returns registered tools and risk metadata.

## Planned API groups

```text
/v1/conversations
/v1/messages
/v1/tasks
/v1/tasks/{id}/cancel
/v1/tasks/{id}/approve
/v1/tasks/{id}/events
/v1/knowledge/documents
/v1/knowledge/search
/v1/memory
/v1/tools
/v1/tools/{id}/execute
/v1/mcp/servers
/v1/mcp/servers/{id}/tools
/v1/connectors
/v1/automations
/v1/evaluations
/v1/audit
/v1/settings
```

## Streaming

Use Server-Sent Events for the first implementation:

`GET /v1/tasks/{id}/events`

Event types:

- `task.created`
- `plan.updated`
- `model.started`
- `model.delta`
- `tool.started`
- `tool.result`
- `approval.required`
- `verification.failed`
- `task.completed`
- `task.failed`

## Idempotency

All external write operations must accept an idempotency key.

## Rate limits

Implement in the edge/API layer. Suggested starter buckets:

- local chat: high;
- cloud calls: limited by provider quota;
- web search: low/moderate;
- write tools: low;
- admin operations: very low.
