# Zero-Budget Operating Strategy

## Principles

Use local/open-source software whenever practical. Treat external free APIs as optional and quota-limited.

## Local layer

- Ollama for inference;
- local embeddings;
- PostgreSQL + pgvector;
- Playwright;
- SearXNG;
- filesystem knowledge base;
- Docker/Podman;
- React/Vite.

## Cloud layer

OpenRouter's free router is the primary burst path. Keep an explicit quota-aware switch so cloud is not called when local capability is sufficient.

## Cost-saving router rules

1. classify task locally;
2. retrieve locally;
3. use the smallest model that passes the task's evaluator;
4. escalate only on complexity, context, modality or low confidence;
5. cache safe, repeatable results;
6. use batch/background processing where a provider supports it;
7. avoid sending private data to cloud providers unless the user has enabled it.

## Hardware profiles

### Low RAM / CPU laptop

- Llama 3.2 1B or Qwen3 1.7B;
- low context;
- local embeddings;
- cloud burst for complex jobs.

### Typical desktop

- Qwen3 4B / Gemma 4 E4B;
- larger context;
- browser and RAG enabled.

### GPU workstation

- larger Qwen/Gemma model;
- parallel tool workers;
- local reranker;
- local multimodal model.

## External API reality

Social platforms, cloud mail, proprietary data sources and some search services generally require credentials and may enforce quotas or paid plans. ORION provides connector interfaces; zero-budget operation does not make third-party APIs free or permissionless.
