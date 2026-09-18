# Memory and Retrieval

## Two stores

**Memory** (`memories`) — durable facts, preferences and interaction summaries the assistant
accumulates. Small, curated, editable by the user.

**Knowledge** (`documents` + `chunks`) — ingested source material. Large, immutable, replaceable.

Both are retrieved on every turn and injected as separately labelled context blocks.

## Embeddings

`services/embeddings.py` tries Ollama `/api/embed` first. On failure it logs once and switches to a
deterministic hashed bag-of-ngrams embedder (blake2b-indexed, signed, L2-normalised). This keeps
ingestion and search fully functional offline with no model download. Results are cached by content
hash.

## Hybrid scoring

```
score = 0.65 · cosine(query, item) + 0.35 · keyword_overlap(query, item)
score *= 0.75 + 0.25 · confidence      # memories only
score += 0.15 if pinned                # memories only
```

Items below `MEMORY_SIMILARITY_MIN` are dropped; if nothing clears the bar, the top three weak
matches are returned so the model still sees something. Knowledge chunks use the same blend without
the confidence and pin terms.

## Chunking

1200 characters with 180 characters of overlap, after whitespace normalisation. Supported formats:
txt, md, pdf (pypdf), docx (python-docx), html (BeautifulSoup), csv, json, yaml, and common source
extensions.

## Write-back

Each completed run stores `Task: … | Outcome: …` as an `interaction_summary` with confidence 0.35 —
low enough that it informs retrieval without competing with user-asserted facts. Explicit facts
written through `memory_write` or the UI default to 0.7–0.95.

## Curation

Use the Memory page to pin authoritative facts, delete wrong ones and inspect confidence. Keys give
you idempotent upserts (`user.tz`, `deploy.topology`), preventing duplicate drift.
