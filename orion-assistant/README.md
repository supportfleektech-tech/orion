# ORION — Local-First Autonomous AI Assistant

ORION is a zero-budget, local-first personal AI assistant architecture designed to feel like a highly capable desktop/web operator without depending on a single paid model provider.

It combines:

- a lightweight local LLM for low-latency everyday work;
- OpenRouter free-model routing for harder cloud tasks;
- persistent memory + RAG over personal files and knowledge;
- an agent loop with planning, tool execution, verification, and memory updates;
- MCP-compatible tool/server architecture;
- web/browser, code, files, database, HTTP/API and automation adapters;
- a responsive dashboard with chat, tasks, memory, knowledge, tools, MCP, automations, connectors, settings and observability;
- strict tool permissions, approvals, audit logging and kill switches;
- a path to voice, social integrations, desktop packaging and multi-agent workflows.

## What "ever learning" means here

ORION does **not** silently retrain model weights or invent permanent beliefs from every conversation. Instead, it continuously improves its *operational knowledge* through validated memory, retrieval, feedback, tool telemetry, evaluations, prompt/policy versioning and optional supervised data collection. Model-weight fine-tuning is a separate, explicit workflow.

## Zero-budget reference stack

| Layer | Default | Purpose |
|---|---|---|
| UI | React + TypeScript + Vite | Fast responsive client |
| API | FastAPI + Python | Async API/orchestration |
| DB | PostgreSQL + pgvector | durable state + vectors |
| Local LLM | Ollama | private, offline inference |
| Embeddings | `nomic-embed-text` via Ollama | local RAG embeddings |
| Cloud LLM | OpenRouter `openrouter/free` | free burst capacity |
| Browser | Playwright | browser automation |
| MCP | MCP server/client adapters | portable tool ecosystem |
| Web search | self-hosted SearXNG adapter | zero vendor-cost search |
| Packaging | Docker Compose | reproducible local environment |

## Current free-model note

OpenRouter currently exposes a free-model router at `openrouter/free`; its free plan currently lists 25+ free models and a 50-request/day rate limit. The available free model pool changes over time, so ORION treats model IDs as configuration rather than hard-coded product guarantees.

Ollama provides OpenAI-compatible APIs and tool calling. Current Ollama libraries include very small local options such as Qwen3 0.6B/1.7B/4B, Llama 3.2 1B/3B and Gemma 4 E2B/E4B, allowing the local model to be matched to available RAM/GPU.

## Quick start

### 1. Prerequisites

- Linux/macOS/Windows with Docker Desktop or Docker Engine
- Python 3.12+
- Node.js 22+
- Optional: Ollama installed locally
- Optional: an OpenRouter API key for cloud burst routing

### 2. Start infrastructure

```bash
cp .env.example .env
./scripts/bootstrap.sh
```

### 3. Start Ollama models

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

For very low-memory devices, change `OLLAMA_MODEL` to `llama3.2:1b` in `.env`. For stronger local reasoning with more hardware, use `gemma4:e4b` or a larger Qwen3/Gemma build.

### 4. Start backend

```bash
./scripts/run-backend.sh
```

### 5. Start frontend

```bash
./scripts/run-frontend.sh
```

Open `http://localhost:5173`.

## Repository map

```text
orion-assistant/
├── README.md
├── LICENSE
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── API_SPEC.md
│   ├── DATA_MODEL.md
│   ├── MEMORY_RAG.md
│   ├── AGENT_RUNTIME.md
│   ├── TOOLS_MCP.md
│   ├── INTEGRATIONS.md
│   ├── UI_SPEC.md
│   ├── SECURITY.md
│   ├── ZERO_BUDGET.md
│   ├── OBSERVABILITY.md
│   ├── EVALUATION.md
│   ├── OPERATIONS.md
│   ├── CURRENT_STACK_NOTES.md
│   └── prompts/
│       ├── system.md
│       ├── planner.md
│       ├── executor.md
│       ├── verifier.md
│       └── memory.md
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── core/config.py
│   │   ├── db/database.py
│   │   ├── db/schema.sql
│   │   ├── api/routes.py
│   │   ├── services/model_router.py
│   │   ├── services/agent_runtime.py
│   │   ├── services/memory.py
│   │   ├── services/embeddings.py
│   │   ├── tools/registry.py
│   │   └── tools/builtin.py
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── index.html
│   └── src/
└── scripts/
    ├── bootstrap.sh
    ├── run-backend.sh
    ├── run-frontend.sh
    ├── ingest.sh
    └── healthcheck.sh
```

## Design principle

The system is intentionally modular. Replace any one model, vector database, search engine, UI framework, MCP implementation or cloud provider without rewriting the agent brain.
# orion
