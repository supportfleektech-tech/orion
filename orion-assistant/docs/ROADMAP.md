# Roadmap

## v1.0.0 — shipped

Complete assistant: chat, agent loop, memory, RAG, governed tools, approvals, kill switch,
automations, observability, settings, Docker deployment and CI.

## v1.1 — depth — shipped

* ✅ Token-level streaming from provider to UI
* ✅ Reranking pass over retrieved chunks
* ✅ Alembic migrations, applied automatically on boot
* ✅ Per-conversation system prompts and personas

## v1.2 — reach

* ✅ MCP client so ORION can consume external MCP servers (see `MCP.md`)
* OAuth connector framework with encrypted secret storage — *still deferred.*
  The Connectors page covers the services ORION actually talks to; anything
  needing real OAuth belongs behind an MCP server you run.
* Cron-expression scheduling in addition to intervals
* ✅ Evaluation harness with regression fixtures and scoring (see `EVALUATION.md`)

## v1.3 — surfaces

* ✅ Voice input/output — local faster-whisper in, on-device Supertonic out,
  plus spoken control of the dashboard (see `VOICE.md`)
* Desktop shell (Tauri)
* Multi-agent planner/executor/verifier split with shared scratchpad

## Principles

1. Zero required spend — every default must work for free and offline.
2. Deny by default — new capabilities ship disabled with a risk tier.
3. Never hard-fail — degrade with an explanation instead of erroring.
4. Observable — anything the agent does must be inspectable afterwards.
