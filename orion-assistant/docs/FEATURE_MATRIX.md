# Feature Matrix (v1.0.0)

| Area | Status | Notes |
|---|---|---|
| Local LLM routing (Ollama) | ✅ | OpenAI-compatible, tool calling |
| Cloud burst (OpenRouter) | ✅ | Ordered failover across fallback models |
| Degraded / offline mode | ✅ | Extractive retrieval answers, never 500s |
| Conversation persistence | ✅ | History, list, load, delete |
| Streaming endpoint | ✅ | SSE at `/v1/chat/stream` |
| Agent tool loop | ✅ | Bounded iterations, full trace |
| Memory store | ✅ | Upsert by key, pin, confidence, CRUD |
| Hybrid retrieval | ✅ | Vector + keyword + confidence + pin boost |
| Embeddings | ✅ | Ollama with deterministic hashed fallback |
| RAG ingestion | ✅ | Upload, paste, path, directory batch |
| Formats | ✅ | txt, md, pdf, docx, html, csv, json, code |
| Tool registry | ✅ | 13 tools, JSON Schema, categories, risk tiers |
| Policy gate | ✅ | Flags, tiers, per-tool enable/disable |
| Approval queue | ✅ | UI + API, approve-and-execute |
| Kill switch | ✅ | Global, instant |
| Audit log | ✅ | All governed events |
| Automations | ✅ | Scheduler, manual run, history |
| Observability | ✅ | Runs, traces, tool history, metrics |
| Live settings | ✅ | Flags, models, loop limits |
| Web search | ✅ | SearXNG adapter (opt-in) |
| HTTP / page fetch | ✅ | Allowlisted (opt-in) |
| Shell sandbox | ✅ | Denylist, timeout, confined cwd (opt-in) |
| Browser automation | ✅ | Playwright (opt-in, requires install) |
| Auth | ✅ | Bearer token, off by default for local use |
| Rate limiting | ✅ | Per IP, per minute |
| Docker packaging | ✅ | Multi-stage, non-root, healthchecks, nginx proxy |
| Postgres + pgvector | ✅ | Compose profile, `DATABASE_URL` switch |
| CI | ✅ | Tests, lint, frontend build, image builds |
| Tests | ✅ | 28 backend tests, ruff clean, strict TS |

## Deliberately out of scope for v1

MCP client federation, voice I/O, OAuth social connectors, desktop packaging, multi-agent
orchestration and model fine-tuning. See `ROADMAP.md`.
