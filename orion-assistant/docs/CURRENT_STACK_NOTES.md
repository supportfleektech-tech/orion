# Current Stack Notes — 18 September 2026

This document records the external assumptions used for the starter design. Provider model catalogs and quotas can change, so model IDs remain environment configuration.

## OpenRouter

- Free Models collection and model catalog are current references.
- `openrouter/free` automatically selects among available free models compatible with request requirements.
- The current Free plan lists 25+ free models, chat/API access and a 50-request/day rate limit.
- Free model availability changes; one model currently listed as going away on 30 September 2026 is Dots3-Note Preview.

References:

- https://openrouter.ai/collections/free-models
- https://openrouter.ai/openrouter/free
- https://openrouter.ai/pricing
- https://openrouter.ai/models?pricing=free

## Ollama

Ollama exposes OpenAI-compatible endpoints and supports tool calling. The current Ollama library contains:

- Qwen3: 0.6B, 1.7B, 4B, 8B, 14B, 30B, 32B, 235B;
- Gemma 4: E2B, E4B, 12B, 26B, 31B;
- Llama 3.2: 1B and 3B.

References:

- https://ollama.com/library/qwen3
- https://ollama.com/library/gemma4
- https://ollama.com/library/llama3.2
- https://ollama.com/blog/tool-support

## Embeddings

The starter uses `nomic-embed-text` through Ollama. It is an embedding-only model and exposes an `/api/embed` endpoint; the common 768-dimension representation is suitable for the included pgvector schema.

Reference:

- https://ollama.com/library/nomic-embed-text

## pgvector

pgvector supports exact and approximate nearest-neighbor search, including HNSW and cosine distance, and can coexist with PostgreSQL full-text search for hybrid retrieval.

Reference:

- https://github.com/pgvector/pgvector

## MCP

MCP exposes tools, resources and prompts. Current ecosystem documentation supports local stdio and remote Streamable HTTP transports, with authorization patterns based on OAuth for protected remote servers. ORION should continue to enforce its own policy gateway around imported MCP capabilities.

References:

- https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- https://csharp.sdk.modelcontextprotocol.io/v2/concepts/transports/transports.html
- https://modelcontextprotocol.io/specification/draft/server/index
