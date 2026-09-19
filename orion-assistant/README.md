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

### Install a real local model

```bash
./scripts/setup-local-model.sh
```

Detects your RAM and disk, installs Ollama, picks the best model your machine can actually run,
pulls it plus the embedder, and writes the settings into `.env`. On an 8 GB machine that is
**`qwen3.5:4b`** — multimodal, 256K context, native tool calling, Apache 2.0.

The **Models** page shows your hardware, the full catalog sized against it, download progress,
and whether the active model supports vision. Auto-selection only picks models with tool
calling, since ORION is an agent. Full details, including an airgapped GGUF path for networks
that block the model registry, are in [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md).

Or set `OPENROUTER_API_KEY` in `.env` to use free cloud routing.

### Talk to it in any format

`POST /v1/chat/upload` (and the paperclip button in Chat) accepts images, PDFs, Word, Excel,
PowerPoint, audio, code and plain text. Documents are text-extracted, images go to the vision
model, audio is transcribed locally with faster-whisper. Anything ORION cannot read is reported
honestly rather than silently ignored — `GET /v1/attachments/capabilities` tells you exactly what
the current deployment supports.

### A control plane that responds

Thirteen pages sharing one tokenised design system. `Ctrl/Cmd+K` opens a
command palette that searches every page and action and falls through to chat
when nothing matches; `?` lists every shortcut. Routes crossfade, lists
stagger, metrics count up, and the mic ring tracks your actual voice level.
All of it collapses to near-zero when the OS asks for reduced motion.

### Speak to it, and let it speak back

Press the microphone (or Ctrl/Cmd+Shift+V) and talk. Speech is transcribed
locally with faster-whisper, replies are spoken by on-device Supertonic TTS, and
you can drive the whole dashboard by voice — "open tools", "enable web search",
"read that back". Enabling a capability always asks first; turning one off never
does. See [docs/VOICE.md](docs/VOICE.md).

### It borrows tools from other assistants

ORION is both an MCP server and an MCP **client**. Point it at any Model Context
Protocol server and its tools join the registry as `server.tool`, policy-gated
at the risk level you assign — a remote server cannot grant itself privilege.
See [docs/MCP.md](docs/MCP.md).

### It tells you when it gets worse

`evals/*.yaml` holds regression cases — a task and what a good answer looks
like. The **Evaluation** page runs them through the real agent loop and grades
them deterministically (no LLM judge), keeping a history so you can tell whether
swapping a model actually helped. See [docs/EVALUATION.md](docs/EVALUATION.md).

### It learns from what works

Successful multi-step runs are distilled into named, reusable **skills** that are injected into
later prompts when they match. Skills gain confidence when they work and are auto-disabled after
repeated failures. Everything is plain text you can read, edit or delete on the **Skills** page.
Thumbs up/down in chat feeds back into the same loop. Disable with `SKILL_LEARNING_ENABLED=false`.

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
* **Optional extras** — `playwright` (browser tool), `mcp` (MCP server and client),
  `faster-whisper` (speech in) and `supertonic` (speech out) are *not* required. Their imports are guarded, and CI asserts the app boots without them. Install from
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

GET    /v1/evaluations                  GET    /v1/mcp/servers
GET    /v1/evaluations/history          POST   /v1/mcp/servers
POST   /v1/evaluations/{name}/run       PATCH  /v1/mcp/servers/{id}
                                        DELETE /v1/mcp/servers/{id}
GET    /v1/personas                     POST   /v1/mcp/servers/{id}/refresh
GET    /v1/voice/status                 POST   /v1/mcp/refresh
GET    /v1/voice/commands
POST   /v1/voice/interpret              GET    /v1/models · /v1/skills
POST   /v1/voice/speak                  GET    /v1/attachments/capabilities
POST   /v1/voice/transcribe
```

---

## Testing and quality

```bash
./scripts/run-tests.sh
```

* 37 frontend tests (Vitest + Testing Library) covering the command palette,
  shortcut overlay and UI primitives, plus 480 backend tests, including the full agent tool-calling loop driven by a mock OpenAI-compatible
  model (multi-step chains, parallel calls, bounded iteration, failure recovery, approval gating,
  kill switch), the SSE token-streaming contract, migration upgrade paths, and real MCP round trips
  against a live server subprocess
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
├── backend/          FastAPI service (app/{api,core,db,services,tools,workers,prompts}), migrations, tests
├── frontend/         React + TypeScript UI (15 fully wired pages)
├── evals/            regression suites (YAML) for the evaluation harness
├── scripts/          bootstrap, dev, tests, healthcheck, ingest, migrate
├── docs/             architecture, API, security, operations, voice, MCP, evaluation, roadmap
├── docker-compose.yml
└── .env.example
```

## Verifying a real model

CI runs against a mock LLM. To prove the real path end to end on your machine:

```bash
./scripts/setup-local-model.sh    # installs Ollama and picks a model for your RAM
./scripts/run-backend.sh
./scripts/verify-real-model.sh    # tool calls, streaming, grounding, memory, evals
```

See [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md) for how to read the results.

Licensed under the terms in `LICENSE`.
