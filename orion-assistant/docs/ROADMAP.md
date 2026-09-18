# ORION End-to-End Roadmap

## Phase 0 — Foundation

- repository and environment management;
- Docker Postgres + pgvector;
- FastAPI API;
- React/Vite client;
- Ollama local model;
- OpenRouter optional cloud route;
- health checks and environment validation.

Exit criteria: browser UI can send a request and receive a model response.

## Phase 1 — Real assistant core

- conversation persistence;
- streaming responses;
- model/tool metadata;
- tool registry;
- policy engine;
- approval records;
- audit events;
- cancellation/timeouts;
- per-task traces.

Exit criteria: a multi-step task can call safe tools, record a trace and finish deterministically.

## Phase 2 — Full RAG

- document ingestion for PDF/DOCX/MD/TXT/code;
- SHA-256 dedupe;
- chunking + metadata;
- local embeddings;
- pgvector HNSW;
- hybrid vector + FTS retrieval;
- optional reranking;
- source citations;
- memory consolidation;
- memory decay / archival.

Exit criteria: ORION can answer questions over a user knowledge folder with source references.

## Phase 3 — Agent runtime

- explicit planner/executor/verifier states;
- task graph / DAG;
- retries with budgets;
- tool result normalization;
- sub-agents for research/coding/data/document tasks;
- result verifier;
- artifact manager;
- resumable tasks.

Exit criteria: multi-step work survives transient failures and can resume.

## Phase 4 — MCP ecosystem

- MCP client adapter;
- local stdio server support;
- Streamable HTTP support;
- server discovery/registry;
- tool capability inspection;
- per-server/per-tool permissions;
- MCP auth/OAuth integration;
- provenance for MCP results.

Exit criteria: install/connect an MCP server and expose selected tools inside ORION's policy gateway.

## Phase 5 — Browser + computer use

- Playwright browser pool;
- isolated browser profiles;
- screenshot/DOM extraction;
- navigation policy;
- download sandbox;
- credential isolation;
- confirmation checkpoints for external writes;
- replayable automation recipes.

Exit criteria: ORION can perform read-only web workflows end-to-end and execute approved write workflows.

## Phase 6 — Integrations

Connector SDK for:

- GitHub/GitLab;
- Google/Microsoft mail and calendar;
- Discord/Slack/Telegram;
- Notion/Google Drive/OneDrive;
- RSS/news;
- databases;
- generic REST/OpenAPI;
- social platforms where official APIs and permitted access exist.

Each connector exposes read/write capabilities separately.

## Phase 7 — Voice + multimodal

- local STT;
- push-to-talk and optional wake word;
- local TTS;
- screenshot/image input;
- document vision;
- voice session state;
- interruption handling.

## Phase 8 — Self-improvement loop

Do not directly self-edit production code or model weights. Instead:

1. collect task traces;
2. detect failure patterns;
3. generate candidate prompt/tool changes;
4. replay regression suite;
5. score against golden tasks;
6. require human approval for policy/security changes;
7. version and canary changes;
8. promote only if quality and safety improve.

## Phase 9 — Packaging

- PWA installability;
- Tauri desktop wrapper;
- background daemon;
- encrypted local secret store;
- device discovery;
- LAN-only mode;
- optional remote access through a secure tunnel.

## Phase 10 — Advanced scale

- multi-agent orchestration;
- model-specific expert pools;
- vector cache;
- semantic result cache;
- local GPU scheduling;
- distributed workers;
- tenant isolation;
- enterprise policies.
