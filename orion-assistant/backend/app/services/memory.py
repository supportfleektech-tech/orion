from __future__ import annotations

from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.embeddings import embed_text
from app.core.config import settings


async def write_memory(
    db: Session,
    content: str,
    kind: str = "fact",
    key: str | None = None,
    source: str = "conversation",
    confidence: float = 0.7,
    metadata: dict | None = None,
) -> str:
    emb = await embed_text(content)
    memory_id = uuid4()
    db.execute(
        text("""
            INSERT INTO memories (id, kind, key, content, source, confidence, metadata, embedding)
            VALUES (:id, :kind, :key, :content, :source, :confidence, CAST(:metadata AS jsonb), CAST(:embedding AS vector))
        """),
        {
            "id": memory_id,
            "kind": kind,
            "key": key,
            "content": content,
            "source": source,
            "confidence": confidence,
            "metadata": __import__("json").dumps(metadata or {}),
            "embedding": "[" + ",".join(str(x) for x in emb) + "]",
        },
    )
    db.commit()
    return str(memory_id)


async def retrieve_memories(db: Session, query: str, limit: int | None = None) -> list[dict]:
    limit = limit or settings.max_context_chunks
    emb = await embed_text(query)
    rows = db.execute(
        text("""
            SELECT id, kind, content, source, confidence,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM memories
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """),
        {"embedding": "[" + ",".join(str(x) for x in emb) + "]", "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows if float(r["score"]) >= settings.memory_similarity_min]
