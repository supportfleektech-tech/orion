# Data Model

## Primary entities

### conversations
Conversation metadata.

### messages
Immutable transcript events. Never overwrite past user messages.

### memories
Durable facts, summaries, preferences, decisions and procedural notes, each with source and confidence.

### documents
One ingested file or web source.

### chunks
Searchable document segments with vector embeddings.

### agent_runs
Long-running task state machine and trace.

### tool_runs
Every tool invocation and its status/result/error.

### approvals
Pending human checkpoints for privileged actions.

### connector_secrets
Indirection records. Production values should live in OS keychains/Vault-like stores, not plaintext DB columns.

### audit_events
Security and operational audit trail.

## Recommended future fields

`tenant_id`, `user_id`, `session_id`, `trace_id`, `parent_run_id`, `policy_snapshot`, `source_uri`, `expires_at`, `content_hash`, `model_revision`, `prompt_revision`.

## Memory lifecycle

```text
capture -> candidate -> validate -> consolidate -> active -> stale -> archive
```

Never treat every model-generated sentence as a truth. Prefer explicit user statements, verified tool results and repeated evidence.
