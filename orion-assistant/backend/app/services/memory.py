from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Memory
from app.services.embeddings import cosine, embed_text, keyword_score


async def write_memory(
    db: Session,
    content: str,
    kind: str = "fact",
    key: str | None = None,
    source: str = "manual",
    confidence: float = 0.6,
    meta: dict | None = None,
) -> str:
    content = content.strip()
    if not content:
        raise ValueError("Memory content cannot be empty")

    embedding = await embed_text(content)
    existing: Memory | None = None
    if key:
        existing = db.scalar(select(Memory).where(Memory.key == key))

    if existing:
        existing.content = content
        existing.kind = kind
        existing.source = source
        existing.confidence = confidence
        existing.embedding = embedding
        existing.meta = meta or existing.meta
        existing.updated_at = datetime.now(UTC)
        db.commit()
        return existing.id

    memory = Memory(
        kind=kind,
        key=key,
        content=content,
        source=source,
        confidence=confidence,
        embedding=embedding,
        meta=meta or {},
    )
    db.add(memory)
    db.commit()
    return memory.id


def _serialize(memory: Memory, score: float) -> dict:
    return {
        "id": memory.id,
        "kind": memory.kind,
        "key": memory.key,
        "content": memory.content,
        "source": memory.source,
        "confidence": memory.confidence,
        "pinned": memory.pinned,
        "score": round(score, 4),
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }


async def retrieve_memories(db: Session, query: str, limit: int | None = None) -> list[dict]:
    """Hybrid retrieval: vector similarity + keyword overlap + confidence prior."""
    limit = limit or settings.max_context_chunks
    rows = db.scalars(select(Memory).order_by(Memory.updated_at.desc()).limit(2000)).all()
    if not rows:
        return []
    qvec = await embed_text(query)

    scored: list[tuple[float, Memory]] = []
    for m in rows:
        vec_score = cosine(qvec, m.embedding or [])
        kw = keyword_score(query, m.content)
        score = 0.65 * vec_score + 0.35 * kw
        score *= 0.75 + 0.25 * float(m.confidence or 0.5)
        if m.pinned:
            score += 0.15
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = [_serialize(m, s) for s, m in scored[:limit] if s >= settings.memory_similarity_min]
    if not out:
        out = [_serialize(m, s) for s, m in scored[:3] if s > 0.05]
    return out


def list_memories(db: Session, kind: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    stmt = select(Memory).order_by(Memory.updated_at.desc()).limit(limit).offset(offset)
    if kind:
        stmt = stmt.where(Memory.kind == kind)
    return [_serialize(m, 0.0) for m in db.scalars(stmt).all()]


def delete_memory(db: Session, memory_id: str) -> bool:
    memory = db.get(Memory, memory_id)
    if not memory:
        return False
    db.delete(memory)
    db.commit()
    return True


def pin_memory(db: Session, memory_id: str, pinned: bool) -> bool:
    memory = db.get(Memory, memory_id)
    if not memory:
        return False
    memory.pinned = pinned
    db.commit()
    return True
