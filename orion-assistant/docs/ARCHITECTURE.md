# Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────┐
│  React + TypeScript UI (Vite)                                │
│  Command Center · Chat · Memory · Knowledge · Tools ·        │
│  Automations · Security · Observability · Settings           │
└───────────────────────────┬──────────────────────────────────┘
                            │ REST (/v1), SSE (/v1/chat/stream)
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI application (app/main.py)                           │
│  GZip · CORS · rate limiting · request timing · error guard  │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  Agent Runtime (services/agent_runtime.py)                   │
│  context build → model call → tool calls → verify → memory   │
└───┬─────────────────┬────────────────────┬───────────────────┘
    │                 │                    │
Model Router     Memory + RAG         Tool Gateway
    │                 │                    │
Ollama/OpenRouter  SQLite/Postgres    Policy · Approvals · Audit
    │                 │                    │
degraded extractive  embeddings      files · web · http · shell · browser
```

## Layers

**API (`app/api`)** — route definitions and Pydantic schemas. Thin: all logic lives in services.

**Core (`app/core`)** — settings (pydantic-settings, env driven), policy engine (risk tiers,
capability flags, kill switch), security (bearer auth, in-memory rate limiter).

**Data (`app/db`)** — SQLAlchemy 2.0 declarative models and engine. `init_db()` creates the schema
on boot, so there is no migration step for the default deployment. SQLite gets WAL and foreign keys
enabled; Postgres works unchanged via `DATABASE_URL`.

**Services (`app/services`)**

| Module | Responsibility |
|---|---|
| `model_router` | Provider selection, ordered failover, statistics, degraded response |
| `embeddings` | Remote embeddings with deterministic hashed fallback, caching, cosine/keyword scoring |
| `memory` | Write/upsert, hybrid retrieval, pin, delete |
| `ingestion` | File reading, chunking, embedding, chunk search, document lifecycle |
| `agent_runtime` | The agent loop, tool dispatch, tracing, audit, memory write-back |
| `fallback` | Extractive retrieval answer when no model is reachable |

**Tools (`app/tools`)** — registry of `ToolDefinition`s with JSON Schema parameters, risk tier and
category. `openai_schemas()` only exposes policy-allowed tools to the model.

**Workers (`app/workers`)** — asyncio scheduler that runs due automations every 30 seconds inside
the API process. No broker required.

## Request flow (chat)

1. Conversation is created or loaded; the user message is persisted.
2. `build_context` retrieves relevant memories and knowledge chunks.
3. Messages are assembled: system prompt, context, recent history, the new turn.
4. The router picks providers in order and calls the first that succeeds.
5. Tool calls are dispatched through the policy gate; high-risk calls create approval requests.
6. The loop repeats until the model stops calling tools or `max_tool_loops` is reached.
7. The run, its trace and an interaction summary memory are persisted; the reply is returned.

## Design decisions

* **SQLite default.** The product must run with one command and no infrastructure. Postgres is a
  configuration change, not a rewrite.
* **Never hard-fail.** Missing model or embedding backends degrade to documented, useful behaviour
  instead of 500s.
* **Deny by default.** Dangerous capabilities are off in configuration and gated again at call time.
* **Everything observable.** Every agent run, tool run and governance decision is recorded and
  surfaced in the UI.
