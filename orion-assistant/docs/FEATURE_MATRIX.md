# Feature Matrix (v1.0.0)

| Area | Status | Notes |
|---|---|---|
| Local LLM routing (Ollama) | ✅ | OpenAI-compatible, tool calling |
| Cloud burst (OpenRouter) | ✅ | Ordered failover across fallback models |
| Degraded / offline mode | ✅ | Extractive retrieval answers, never 500s |
| Conversation persistence | ✅ | History, list, load, delete, pin, rename, archive |
| Streaming | ✅ | Incremental SSE with token-by-token output, wired into the chat UI with live tool chips |
| Agent tool loop | ✅ | Bounded iterations, full trace |
| Memory store | ✅ | Upsert by key, pin, confidence, CRUD |
| Hybrid retrieval | ✅ | Vector + keyword + confidence + pin boost |
| Reranking | ✅ | Retrieval, BM25, coverage and proximity blended over the candidate set |
| Embeddings | ✅ | Ollama with deterministic hashed fallback |
| RAG ingestion | ✅ | Upload, paste, path, directory batch |
| Formats (knowledge) | ✅ | txt, md, pdf, docx, html, csv, json, code |
| Multimodal chat input | ✅ | Images to vision models; pdf/docx/pptx/xlsx extracted; audio transcribed; unreadable files reported honestly |
| Model provisioning | ✅ | Hardware detection, tier ladder, one-command installer, in-UI download with progress |
| Skill learning | ✅ | Successful runs distilled into reusable procedures, confidence reinforcement, auto-disable |
| Feedback loop | ✅ | Thumbs up/down feeding skill confidence |
| Tool registry | ✅ | 13 builtin tools, JSON Schema, categories, risk tiers |
| MCP server | ✅ | Read-only surface over memory and knowledge (opt-in) |
| MCP client | ✅ | Register external servers; tools namespaced `server.tool` and policy-gated |
| Conversation personas | ✅ | 5 presets plus a per-conversation system prompt, layered under the safety rules |
| Voice input | ✅ | Browser recogniser with a local faster-whisper fallback |
| Voice output | ✅ | On-device Supertonic TTS, optional autoplay |
| Voice control | ✅ | Spoken navigation, capability toggles and playback; confirmation for anything that grants access |
| Policy gate | ✅ | Flags, tiers, per-tool enable/disable |
| Approval queue | ✅ | UI + API, approve-and-execute |
| Kill switch | ✅ | Global, instant |
| Audit log | ✅ | All governed events |
| Automations | ✅ | Scheduler, manual run, history |
| Observability | ✅ | Runs, traces, tool history, metrics |
| Evaluation harness | ✅ | YAML suites graded deterministically against the live agent, with run history |
| Live settings | ✅ | Flags, models, loop limits; persisted across restarts |
| Web search | ✅ | SearXNG adapter (opt-in) |
| HTTP / page fetch | ✅ | Allowlisted (opt-in) |
| Shell sandbox | ✅ | Denylist, timeout, confined cwd (opt-in) |
| Browser automation | ✅ | Playwright (opt-in, requires install) |
| Auth | ✅ | Bearer token, off by default for local use |
| Rate limiting | ✅ | Per IP, per minute |
| Schema migrations | ✅ | Alembic, auto-upgrade on boot, revision reported at `/health` |
| Docker packaging | ✅ | Multi-stage, non-root, healthchecks, nginx proxy |
| Postgres + pgvector | ✅ | Compose profile, `DATABASE_URL` switch |
| CI | ✅ | Tests, lint, frontend build, image builds |
| Tests | ✅ | 359 backend tests incl. agent loop, token streaming, reranking, migrations, multimodal, skills, voice, real MCP round trips; ruff clean, strict TS |

## Deliberately out of scope for v1

OAuth social connectors, desktop packaging, multi-agent
orchestration and model fine-tuning (ORION improves via memory, knowledge and skills instead —
see `LOCAL_MODELS.md`). Video is accepted but not analysed frame-by-frame, and scanned documents
are not OCR'd. See `ROADMAP.md`.
