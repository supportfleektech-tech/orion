# Memory + RAG Design

## Retrieval pipeline

```text
query
  ↓
intent + filters
  ↓
query rewrite (optional)
  ↓
vector retrieval ─┐
                  ├─ rank fusion ─→ rerank ─→ context pack
full-text search ─┘
  ↓
answer with source attribution
```

## Chunking

Starter defaults:

- 1,200 characters per chunk;
- 180-character overlap;
- preserve document name/path metadata;
- do not split structured code blocks when avoidable;
- add page/section metadata for PDFs/docs in production.

## Hybrid search

Use pgvector cosine similarity plus PostgreSQL full-text search, then Reciprocal Rank Fusion (RRF):

`RRF(d) = Σ 1 / (k + rank_i(d))`

A later stage can use a local cross-encoder reranker.

## Context packing

Prefer:

1. high similarity;
2. diverse sources;
3. current versions;
4. direct evidence;
5. user-scoped data.

Cap context to protect model latency and prevent unrelated memory flooding.

## Memory types

- `user_preference`
- `project_fact`
- `decision`
- `relationship`
- `task_summary`
- `procedure`
- `interaction_summary`
- `knowledge_source`

## Consolidation

A periodic job should merge duplicate memories, update confidence and mark contradictions rather than silently choosing one.

## Privacy

Provide a UI action for every memory:

- view;
- edit;
- forget;
- source;
- confidence;
- scope.
