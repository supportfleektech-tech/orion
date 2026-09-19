# Data Model

SQLAlchemy 2.0 declarative models in `backend/app/db/models.py`. Created automatically by
`init_db()` at startup on both SQLite and Postgres.

| Table | Purpose | Key columns |
|---|---|---|
| `conversations` | Chat threads | `id`, `title`, `pinned`, `archived`, `updated_at` |
| `messages` | Turns | `conversation_id`, `role`, `content`, `provider`, `model`, `latency_ms`, `meta` |
| `memories` | Long-term memory | `kind`, `key` (unique-ish upsert handle), `content`, `source`, `confidence`, `pinned`, `embedding` |
| `documents` | Ingested sources | `name`, `path`, `hash` (dedupe), `size_bytes`, `chunk_count` |
| `chunks` | RAG units | `document_id`, `chunk_index`, `content`, `embedding`, `meta` |
| `tool_runs` | Tool telemetry | `tool_name`, `arguments`, `result`, `risk`, `status`, `duration_ms`, `error` |
| `agent_runs` | Agent telemetry | `task`, `state`, `provider`, `model`, `result`, `trace`, `duration_ms` |
| `approvals` | Human-in-the-loop | `tool_name`, `arguments`, `reason`, `status`, `result`, `resolved_at` |
| `automations` | Scheduled work | `name`, `prompt`, `schedule_seconds`, `enabled`, `last_run_at`, `last_status`, `last_result` |
| `audit_events` | Governance log | `event_type`, `actor`, `summary`, `details` |
| `settings` | Persisted overrides | `key`, `value` |

## Embeddings

Stored as JSON arrays for portability across SQLite and Postgres, and scored in Python
(`services/embeddings.cosine`). With Postgres + pgvector you can add native `vector` columns and an
HNSW index for large corpora; the retrieval functions are the only code that needs to change.

Dimension is `EMBEDDING_DIM` (default 768, matching `nomic-embed-text`). The hashed fallback
embedder produces the same dimensionality, so the two are interchangeable at the storage layer —
though mixing them within one corpus lowers recall. Re-ingest after switching embedders.

## Lifecycle

* Documents deduplicate on content hash; re-ingesting the same path replaces prior chunks.
* Deleting a document cascades to its chunks; deleting a conversation cascades to its messages.
* Each completed agent run writes a low-confidence `interaction_summary` memory so the assistant
  accumulates operational context without asserting new facts.
