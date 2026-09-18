from __future__ import annotations

import httpx
from app.core.config import settings


async def embed_text(text: str) -> list[float]:
    """Create a local embedding through Ollama; keeps RAG zero-cost and private."""
    base = settings.ollama_base_url.removesuffix("/v1")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{base}/api/embed",
            json={"model": settings.ollama_embed_model, "input": text},
        )
        r.raise_for_status()
        data = r.json()
        embeddings = data.get("embeddings")
        if not embeddings:
            raise RuntimeError("Embedding model returned no embeddings")
        return embeddings[0]
