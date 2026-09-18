# ORION — Local-First Autonomous AI Assistant

ORION is a production-ready, zero-budget personal AI operating system. It runs entirely on your
machine, keeps your data local, and only reaches the cloud when you allow it to.

**Status: v1.0.0 — complete and deployable.** Backend, frontend, agent runtime, retrieval,
governance, automations, Docker packaging and CI are all implemented and tested.

---

## What it does

| Capability | Implementation |
|---|---|
| **Chat** | Multi-turn conversations with history, persistence, routing mode selection, pin/rename/archive |
| **Agent runtime** | Tool-calling loop with context injection, tracing, bounded iterations, and live SSE streaming of tool activity |
| **Model routing** | Local-first (Ollama) → cloud burst (OpenRouter free tier) → graceful degraded mode |
| **Memory** | Hybrid retrieval (vector + keyword + confidence + pinning), upsert by key, CRUD |
| **Knowledge / RAG** | Upload, paste or ingest paths; chunking, embedding, semantic search, library management |
| **Tools** | 13 built-in governed tools: math, time, files, knowledge, memory, web search, HTTP, page fetch, shell, browser |
| **Policy & approvals** | Risk tiers, capability flags, approval queue, global kill switch, full audit log |
| **Automations** | Recurring agent tasks with an in-process scheduler, manual run and result history |
| **Observability** | Agent run traces, tool run history, success rates, latency, router statistics |
| **Settings** | Live runtime configuration of flags, models and loop limits, persisted across restarts |

### Works offline, always

ORION never hard-fails when no model is available. If neither Ollama nor OpenRouter is reachable
it switches to **retrieval-only mode**: it answers by assembling the most relevant sentences from
your memories and knowledge base, clearly labelled with their sources. Embeddings fall back to a
deterministic local hashed embedder, so ingestion and search keep working with zero dependencies.

---

## Quick start

### Option A — Docker (recommended for deployment)

```bash
cd orion-assistant
cp .env.example .env         # review the settings
docker compose up -d --build
```

* UI: <http://localhost:8080>
* API: <http://localhost:8000> · docs at `/docs`

Optional profiles:

```bash
docker compose --profile postgres up -d     # Postgres + pgvector instead of SQLite
docker compose --profile web-search up -d   # self-hosted SearXNG for web_search
```

### Option B — Local development

```bash
cd orion-assistant
./scripts/bootstrap.sh   # venv + npm install + .env
./scripts/dev.sh         # API on :8000, UI on :5173 (proxied)
```

Open <http://localhost:5173>. The Vite dev server proxies `/v1`, `/health` and `/docs` to the API,
so no CORS configuration is needed.

### Try it with no model installed

```bash
python3 scripts/demo_model.py 11435 &          # deterministic demo responder
OLLAMA_BASE_URL=http://127.0.0.1:11435/v1 OLLAMA_MODEL=orion-demo ./scripts/run-backend.sh
```

`scripts/demo_model.py` is **not an LLM** — it is a rule-based responder that speaks the OpenAI
chat-completions protocol including tool calling, so you can exercise the complete agent loop
(tool selection → execution → result → answer) with no download and no API key. Ask it to
calculate something, check the time, list files, or search memory.

### Enable generative answers

```bash
ollama pull qwen3:4b          # or llama3.2:1b on low-memory machines
ollama pull nomic-embed-text  # better embeddings than the built-in fallback
```

Or set `OPENROUTER_API_KEY` in `.env` to use free cloud routing.

---

## Architecture

```
React + TypeScript UI  ──►  FastAPI  ──►  Agent Runtime
                                            │
        ┌───────────────────────────────────┼─────────────────────────────┐
   Model Router                        Memory + RAG                  Tool Gateway
        │                                   │                             │
 Ollama ─┴─ OpenRouter            SQLite / Postgres+pgvector       Policy · Approvals · Audit
        │                                                                  │
 degraded extractive mode                                    files · web · http · shell · browser
```

* **Storage** — SQLite by default (zero infrastructure). Point `DATABASE_URL` at
  `postgresql+psycopg://…` for Postgres + pgvector at scale. Schema is created automatically on boot.
* **Embeddings** — `nomic-embed-text` via Ollama when available, otherwise a deterministic hashed
  bag-of-ngrams embedder so retrieval never breaks.
* **Optional extras** — `playwright` (browser tool) and `mcp` (read-only MCP surface) are *not*
  required. Their imports are guarded, and CI asserts the app boots without them. Install from
  `backend/requirements-optional.txt` only if you need those capabilities.
* **Safety** — every tool declares a risk tier. `high` and `destructive` tools create an approval
  request instead of executing. Category flags (`shell`, `browser`, `network`, web search) are off by
  default. A global kill switch halts all tool use instantly. Everything is audited.

---

## API surface

Full interactive documentation at `/docs`. Highlights:

```
GET    /health                          POST   /v1/chat
GET    /v1/system/status                POST   /v1/chat/stream          (SSE)
GET    /v1/system/metrics               GET    /v1/conversations
                                        GET    /v1/conversations/{id}
POST   /v1/memory                       DELETE /v1/conversations/{id}
GET    /v1/memory
GET    /v1/memory/search?q=             GET    /v1/tools
POST   /v1/memory/{id}/pin              POST   /v1/tools/run
DELETE /v1/memory/{id}                  POST   /v1/tools/{name}/toggle
                                        GET    /v1/tools/runs
POST   /v1/knowledge/upload
POST   /v1/knowledge/ingest             GET    /v1/approvals
POST   /v1/knowledge/ingest-text        POST   /v1/approvals/{id}
GET    /v1/knowledge/search?q=          POST   /v1/security/kill-switch
GET    /v1/knowledge/documents
DELETE /v1/knowledge/documents/{id}     GET    /v1/automations
                                        POST   /v1/automations
GET    /v1/runs · /v1/runs/{id}         POST   /v1/automations/{id}/run
GET    /v1/audit                        DELETE /v1/automations/{id}
GET    /v1/settings · PATCH /v1/settings
```

---

## Testing and quality

```bash
./scripts/run-tests.sh
```

* 69 backend tests, including the full agent tool-calling loop driven by a mock OpenAI-compatible
  model (multi-step chains, parallel calls, bounded iteration, failure recovery, approval gating,
  kill switch) and the SSE streaming contract
* `ruff` lint clean
* Strict TypeScript build with `noUnusedLocals` / `noUnusedParameters`
* GitHub Actions runs backend tests, a production-dependency boot check, the frontend build and both Docker image builds

---

## Production checklist

1. Set `AUTH_ENABLED=true` and a strong `ADMIN_TOKEN` before exposing the API beyond localhost.
2. Restrict `CORS_ORIGINS` to your actual UI origin.
3. Keep `ALLOW_SHELL_TOOL`, `ALLOW_BROWSER_TOOL` and `ALLOW_NETWORK_TOOL` off unless required;
   when enabling network tools, set `HTTP_ALLOWLIST`.
4. Use the Postgres profile and back up the `orion-data` volume.
5. Terminate TLS at your reverse proxy; nginx already sets baseline security headers.
6. Review the audit log (`/v1/audit`) and approval queue regularly.

## Repository layout

```
orion-assistant/
├── backend/          FastAPI service (app/{api,core,db,services,tools,workers,prompts}) + tests
├── frontend/         React + TypeScript UI (9 fully wired pages)
├── scripts/          bootstrap, dev, tests, healthcheck, ingest
├── docs/             architecture, API, security, operations, roadmap
├── docker-compose.yml
└── .env.example
```

Licensed under the terms in `LICENSE`.
