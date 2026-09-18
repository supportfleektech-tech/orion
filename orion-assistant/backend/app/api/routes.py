from __future__ import annotations

from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.agent_runtime import run_agent
from app.services.memory import write_memory, retrieve_memories
from app.services.ingestion import ingest_path
from app.tools.registry import registry

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = None
    mode: str = "auto"


class IngestRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class MemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    kind: str = "fact"
    key: str | None = None
    confidence: float = 0.7


@router.get("/health")
def health():
    return {"ok": True, "service": "orion-api"}


@router.get("/v1/tools")
def list_tools():
    return {
        "tools": [
            {"name": t.name, "description": t.description, "risk": t.risk, "requires_confirmation": t.requires_confirmation}
            for t in registry.list()
        ]
    }


@router.post("/v1/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    conversation_id = req.conversation_id or str(uuid4())
    db.execute(text("""
        INSERT INTO conversations (id, title) VALUES (:id, :title)
        ON CONFLICT (id) DO NOTHING
    """), {"id": conversation_id, "title": req.message[:80]})
    db.execute(text("INSERT INTO messages (conversation_id, role, content) VALUES (:cid, 'user', :content)"), {"cid": conversation_id, "content": req.message})
    db.commit()

    out = await run_agent(db, req.message, conversation_id=conversation_id, mode=req.mode)
    db.execute(text("INSERT INTO messages (conversation_id, role, content, provider, model) VALUES (:cid, 'assistant', :content, :provider, :model)"), {
        "cid": conversation_id,
        "content": out["result"],
        "provider": out["provider"],
        "model": out["model"],
    })
    db.commit()
    return {"conversation_id": conversation_id, **out}


@router.post("/v1/knowledge/ingest")
async def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    return await ingest_path(db, req.path)


@router.post("/v1/memory")
async def add_memory(req: MemoryRequest, db: Session = Depends(get_db)):
    memory_id = await write_memory(db, req.content, req.kind, req.key, "manual", req.confidence)
    return {"id": memory_id}


@router.get("/v1/memory/search")
async def search_memory(q: str, db: Session = Depends(get_db)):
    return {"results": await retrieve_memories(db, q)}
