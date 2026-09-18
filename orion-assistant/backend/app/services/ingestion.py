from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader
from docx import Document as DocxDocument
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.embeddings import embed_text

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180


def read_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown", ".json", ".csv", ".py", ".js", ".ts", ".tsx", ".html", ".css"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(text_value: str) -> list[str]:
    text_value = " ".join(text_value.split())
    if not text_value:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text_value):
        end = min(len(text_value), start + CHUNK_SIZE)
        chunks.append(text_value[start:end])
        if end >= len(text_value):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


async def ingest_path(db: Session, path: str) -> dict:
    p = Path(path).resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(path)
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.execute(text("SELECT id FROM documents WHERE hash=:hash"), {"hash": digest}).scalar()
    if existing:
        return {"document_id": str(existing), "skipped": True}

    content = read_source(p)
    doc_id = uuid4()
    db.execute(text("INSERT INTO documents (id,name,path,mime_type,hash,metadata) VALUES (:id,:name,:path,:mime,:hash,CAST(:metadata AS jsonb))"), {
        "id": doc_id,
        "name": p.name,
        "path": str(p),
        "mime": p.suffix.lower(),
        "hash": digest,
        "metadata": json.dumps({"size": len(raw)}),
    })

    for idx, chunk in enumerate(chunk_text(content)):
        emb = await embed_text(chunk)
        db.execute(text("""
            INSERT INTO chunks (id, document_id, chunk_index, content, metadata, embedding)
            VALUES (:id, :doc_id, :idx, :content, CAST(:metadata AS jsonb), CAST(:embedding AS vector))
        """), {
            "id": uuid4(),
            "doc_id": doc_id,
            "idx": idx,
            "content": chunk,
            "metadata": json.dumps({"source": str(p)}),
            "embedding": "[" + ",".join(str(x) for x in emb) + "]",
        })
    db.commit()
    return {"document_id": str(doc_id), "chunks": len(chunk_text(content)), "skipped": False}
