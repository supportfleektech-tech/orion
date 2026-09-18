from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ApprovalDecision,
    AutomationRequest,
    ChatRequest,
    IngestRequest,
    IngestTextRequest,
    KillSwitchRequest,
    MemoryRequest,
    SettingsPatch,
    ToolRunRequest,
    ToolToggleRequest,
)
from app.core.config import settings
from app.core.policy import kill_switch_state, set_kill_switch
from app.core.security import require_auth
from app.db.database import get_db
from app.db.models import (
    AgentRun,
    Approval,
    AuditEvent,
    Automation,
    Chunk,
    Conversation,
    Document,
    Memory,
    Message,
    ToolRun,
)
from app.services.agent_runtime import audit, execute_tool, run_agent, stream_agent
from app.services.ingestion import (
    delete_document,
    ingest_path,
    ingest_text,
    knowledge_root,
    list_documents,
    search_chunks,
)
from app.services.memory import delete_memory, list_memories, pin_memory, retrieve_memories, write_memory
from app.services.model_router import router as model_router
from app.tools.registry import registry

router = APIRouter()
BOOT_TIME = time.time()


# ---------------------------------------------------------------- health / meta
@router.get("/health", tags=["system"])
def health():
    return {
        "ok": True,
        "service": "orion-api",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": int(time.time() - BOOT_TIME),
    }


@router.get("/v1/system/status", tags=["system"])
async def system_status(db: Session = Depends(get_db)):
    providers = await model_router.health()
    counts = {
        "conversations": db.scalar(select(func.count()).select_from(Conversation)) or 0,
        "messages": db.scalar(select(func.count()).select_from(Message)) or 0,
        "memories": db.scalar(select(func.count()).select_from(Memory)) or 0,
        "documents": db.scalar(select(func.count()).select_from(Document)) or 0,
        "chunks": db.scalar(select(func.count()).select_from(Chunk)) or 0,
        "tool_runs": db.scalar(select(func.count()).select_from(ToolRun)) or 0,
        "agent_runs": db.scalar(select(func.count()).select_from(AgentRun)) or 0,
        "pending_approvals": db.scalar(
            select(func.count()).select_from(Approval).where(Approval.status == "pending")
        ) or 0,
    }
    tools = registry.as_dicts()
    return {
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": int(time.time() - BOOT_TIME),
        "providers": providers,
        "degraded": not providers["local"]["reachable"] and not providers["cloud"]["reachable"],
        "counts": counts,
        "tools": {"total": len(tools), "enabled": sum(1 for t in tools if t["allowed"])},
        "router_stats": model_router.stats,
        "kill_switch": kill_switch_state(),
        "flags": {
            "local_only": settings.local_only,
            "cloud_escalation_enabled": settings.cloud_escalation_enabled,
            "enable_web_search": settings.enable_web_search,
            "allow_shell_tool": settings.allow_shell_tool,
            "allow_browser_tool": settings.allow_browser_tool,
            "allow_network_tool": settings.allow_network_tool,
            "auth_enabled": settings.auth_enabled,
        },
        "models": {"local": settings.ollama_model, "cloud": settings.openrouter_model},
    }


@router.get("/v1/system/metrics", tags=["system"])
def metrics(db: Session = Depends(get_db)):
    runs = db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(50)).all()
    tool_runs = db.scalars(select(ToolRun).order_by(ToolRun.created_at.desc()).limit(50)).all()
    avg_latency = int(sum(r.duration_ms for r in runs) / len(runs)) if runs else 0
    return {
        "agent_runs_recent": len(runs),
        "agent_success_rate": round(
            sum(1 for r in runs if r.state == "succeeded") / len(runs), 3
        ) if runs else 1.0,
        "avg_run_ms": avg_latency,
        "tool_success_rate": round(
            sum(1 for t in tool_runs if t.status == "succeeded") / len(tool_runs), 3
        ) if tool_runs else 1.0,
        "router": model_router.stats,
        "timeline": [
            {
                "id": r.id,
                "task": r.task[:120],
                "state": r.state,
                "provider": r.provider,
                "model": r.model,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs[:20]
        ],
    }


# ---------------------------------------------------------------- chat
@router.post("/v1/chat", tags=["chat"], dependencies=[Depends(require_auth)])
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, req.conversation_id) if req.conversation_id else None
    if conversation is None:
        conversation = Conversation(title=req.message[:80] or "New conversation")
        if req.conversation_id:
            conversation.id = req.conversation_id
        db.add(conversation)
        db.commit()

    db.add(Message(conversation_id=conversation.id, role="user", content=req.message))
    conversation.updated_at = datetime.now(UTC)
    db.commit()

    out = await run_agent(
        db, req.message, conversation_id=conversation.id, mode=req.mode, auto_approve=req.auto_approve
    )
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=out["result"],
            provider=out["provider"],
            model=out["model"],
            latency_ms=out["duration_ms"],
            meta={"degraded": out["degraded"]},
        )
    )
    db.commit()
    return {"conversation_id": conversation.id, **out}


@router.post("/v1/chat/stream", tags=["chat"], dependencies=[Depends(require_auth)])
async def chat_stream(req: ChatRequest, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, req.conversation_id) if req.conversation_id else None
    if conversation is None:
        conversation = Conversation(title=req.message[:80] or "New conversation")
        db.add(conversation)
        db.commit()
    db.add(Message(conversation_id=conversation.id, role="user", content=req.message))
    db.commit()

    async def generator():
        yield f'event: start\ndata: {{"conversation_id": "{conversation.id}"}}\n\n'
        final = ""
        async for event in stream_agent(db, req.message, conversation.id, req.mode):
            if event.startswith("event: message"):
                import json as _json

                final = _json.loads(event.split("data: ", 1)[1].strip())["content"]
            yield event
        db.add(Message(conversation_id=conversation.id, role="assistant", content=final))
        db.commit()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/v1/conversations", tags=["chat"])
def list_conversations(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(
        select(Conversation).where(Conversation.archived.is_(False)).order_by(Conversation.updated_at.desc()).limit(limit)
    ).all()
    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "pinned": c.pinned,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "message_count": db.scalar(
                    select(func.count()).select_from(Message).where(Message.conversation_id == c.id)
                ),
            }
            for c in rows
        ]
    }


@router.get("/v1/conversations/{conversation_id}", tags=["chat"])
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()
    return {
        "id": conversation.id,
        "title": conversation.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "provider": m.provider,
                "model": m.model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/v1/conversations/{conversation_id}", tags=["chat"], dependencies=[Depends(require_auth)])
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    db.delete(conversation)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------- memory
@router.post("/v1/memory", tags=["memory"], dependencies=[Depends(require_auth)])
async def add_memory(req: MemoryRequest, db: Session = Depends(get_db)):
    memory_id = await write_memory(db, req.content, req.kind, req.key, "manual", req.confidence, req.meta)
    return {"id": memory_id}


@router.get("/v1/memory", tags=["memory"])
def get_memories(db: Session = Depends(get_db), kind: str | None = None, limit: int = 100, offset: int = 0):
    return {"memories": list_memories(db, kind, limit, offset)}


@router.get("/v1/memory/search", tags=["memory"])
async def search_memory(q: str = Query(min_length=1), limit: int = 8, db: Session = Depends(get_db)):
    return {"results": await retrieve_memories(db, q, limit)}


@router.post("/v1/memory/{memory_id}/pin", tags=["memory"], dependencies=[Depends(require_auth)])
def pin(memory_id: str, pinned: bool = True, db: Session = Depends(get_db)):
    if not pin_memory(db, memory_id, pinned):
        raise HTTPException(404, "Memory not found")
    return {"id": memory_id, "pinned": pinned}


@router.delete("/v1/memory/{memory_id}", tags=["memory"], dependencies=[Depends(require_auth)])
def remove_memory(memory_id: str, db: Session = Depends(get_db)):
    if not delete_memory(db, memory_id):
        raise HTTPException(404, "Memory not found")
    return {"deleted": True}


# ---------------------------------------------------------------- knowledge
@router.get("/v1/knowledge/documents", tags=["knowledge"])
def documents(db: Session = Depends(get_db)):
    return {"documents": list_documents(db)}


@router.post("/v1/knowledge/ingest", tags=["knowledge"], dependencies=[Depends(require_auth)])
async def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    try:
        return await ingest_path(db, req.path)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/v1/knowledge/ingest-text", tags=["knowledge"], dependencies=[Depends(require_auth)])
async def ingest_inline(req: IngestTextRequest, db: Session = Depends(get_db)):
    return await ingest_text(db, req.name, req.content, f"inline://{req.name}")


@router.post("/v1/knowledge/upload", tags=["knowledge"], dependencies=[Depends(require_auth)])
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    root = knowledge_root()
    target = root / (file.filename or "upload.txt")
    data = await file.read()
    target.write_bytes(data)
    try:
        return await ingest_path(db, str(target))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/v1/knowledge/search", tags=["knowledge"])
async def knowledge_search(q: str = Query(min_length=1), limit: int = 8, db: Session = Depends(get_db)):
    return {"results": await search_chunks(db, q, limit)}


@router.delete("/v1/knowledge/documents/{document_id}", tags=["knowledge"], dependencies=[Depends(require_auth)])
def remove_document(document_id: str, db: Session = Depends(get_db)):
    if not delete_document(db, document_id):
        raise HTTPException(404, "Document not found")
    return {"deleted": True}


# ---------------------------------------------------------------- tools
@router.get("/v1/tools", tags=["tools"])
def list_tools():
    return {"tools": registry.as_dicts()}


@router.post("/v1/tools/run", tags=["tools"], dependencies=[Depends(require_auth)])
async def run_tool(req: ToolRunRequest, db: Session = Depends(get_db)):
    result = await execute_tool(db, req.name, req.arguments, auto_approve=req.auto_approve)
    if not result.get("ok") and not result.get("approval_required"):
        raise HTTPException(400, result.get("error", "Tool execution failed"))
    return result


@router.post("/v1/tools/{name}/toggle", tags=["tools"], dependencies=[Depends(require_auth)])
def toggle_tool(name: str, req: ToolToggleRequest, db: Session = Depends(get_db)):
    if not registry.set_enabled(name, req.enabled):
        raise HTTPException(404, "Tool not found")
    audit(db, "tool.toggled", f"{name} enabled={req.enabled}")
    return {"name": name, "enabled": req.enabled}


@router.get("/v1/tools/runs", tags=["tools"])
def tool_runs(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(select(ToolRun).order_by(ToolRun.created_at.desc()).limit(limit)).all()
    return {
        "runs": [
            {
                "id": r.id,
                "tool_name": r.tool_name,
                "status": r.status,
                "risk": r.risk,
                "duration_ms": r.duration_ms,
                "error": r.error,
                "arguments": r.arguments,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------- approvals
@router.get("/v1/approvals", tags=["security"])
def approvals(db: Session = Depends(get_db), status_filter: str = "pending"):
    stmt = select(Approval).order_by(Approval.created_at.desc()).limit(100)
    if status_filter != "all":
        stmt = stmt.where(Approval.status == status_filter)
    return {
        "approvals": [
            {
                "id": a.id,
                "tool_name": a.tool_name,
                "arguments": a.arguments,
                "reason": a.reason,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in db.scalars(stmt).all()
        ]
    }


@router.post("/v1/approvals/{approval_id}", tags=["security"], dependencies=[Depends(require_auth)])
async def resolve_approval(approval_id: str, decision: ApprovalDecision, db: Session = Depends(get_db)):
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    if approval.status != "pending":
        raise HTTPException(409, f"Approval already {approval.status}")

    approval.status = "approved" if decision.approve else "rejected"
    approval.resolved_at = datetime.now(UTC)
    db.commit()
    audit(db, "approval.resolved", f"{approval.tool_name} {approval.status}", {"id": approval.id}, actor="user")

    result = None
    if decision.approve and decision.execute:
        result = await execute_tool(db, approval.tool_name, approval.arguments, auto_approve=True)
        approval.result = result
        db.commit()
    return {"id": approval.id, "status": approval.status, "result": result}


# ---------------------------------------------------------------- automations
@router.get("/v1/automations", tags=["automations"])
def get_automations(db: Session = Depends(get_db)):
    rows = db.scalars(select(Automation).order_by(Automation.created_at.desc())).all()
    return {
        "automations": [
            {
                "id": a.id,
                "name": a.name,
                "prompt": a.prompt,
                "schedule_seconds": a.schedule_seconds,
                "enabled": a.enabled,
                "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
                "last_status": a.last_status,
                "last_result": (a.last_result or "")[:500],
            }
            for a in rows
        ]
    }


@router.post("/v1/automations", tags=["automations"], dependencies=[Depends(require_auth)])
def create_automation(req: AutomationRequest, db: Session = Depends(get_db)):
    automation = Automation(**req.model_dump())
    db.add(automation)
    db.commit()
    return {"id": automation.id}


@router.post("/v1/automations/{automation_id}/run", tags=["automations"], dependencies=[Depends(require_auth)])
async def run_automation(automation_id: str, db: Session = Depends(get_db)):
    automation = db.get(Automation, automation_id)
    if not automation:
        raise HTTPException(404, "Automation not found")
    out = await run_agent(db, automation.prompt, mode="auto")
    automation.last_run_at = datetime.now(UTC)
    automation.last_status = "succeeded" if not out["degraded"] else "degraded"
    automation.last_result = out["result"][:4000]
    db.commit()
    return {"id": automation.id, "result": out["result"], "provider": out["provider"]}


@router.delete("/v1/automations/{automation_id}", tags=["automations"], dependencies=[Depends(require_auth)])
def delete_automation(automation_id: str, db: Session = Depends(get_db)):
    automation = db.get(Automation, automation_id)
    if not automation:
        raise HTTPException(404, "Automation not found")
    db.delete(automation)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------- runs / audit / settings
@router.get("/v1/runs", tags=["observability"])
def agent_runs(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)).all()
    return {
        "runs": [
            {
                "id": r.id,
                "task": r.task,
                "state": r.state,
                "provider": r.provider,
                "model": r.model,
                "duration_ms": r.duration_ms,
                "result": (r.result or "")[:600],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.get("/v1/runs/{run_id}", tags=["observability"])
def agent_run_detail(run_id: str, db: Session = Depends(get_db)):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {
        "id": run.id,
        "task": run.task,
        "state": run.state,
        "provider": run.provider,
        "model": run.model,
        "result": run.result,
        "trace": run.trace,
        "duration_ms": run.duration_ms,
    }


@router.get("/v1/audit", tags=["observability"])
def audit_events(db: Session = Depends(get_db), limit: int = 100):
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)).all()
    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor": e.actor,
                "summary": e.summary,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ]
    }


@router.get("/v1/settings", tags=["settings"])
def get_settings_endpoint():
    return {
        "local_only": settings.local_only,
        "cloud_escalation_enabled": settings.cloud_escalation_enabled,
        "enable_web_search": settings.enable_web_search,
        "allow_shell_tool": settings.allow_shell_tool,
        "allow_browser_tool": settings.allow_browser_tool,
        "allow_network_tool": settings.allow_network_tool,
        "ollama_model": settings.ollama_model,
        "openrouter_model": settings.openrouter_model,
        "max_tool_loops": settings.max_tool_loops,
        "auth_enabled": settings.auth_enabled,
        "environment": settings.environment,
    }


@router.patch("/v1/settings", tags=["settings"], dependencies=[Depends(require_auth)])
def patch_settings(patch: SettingsPatch, db: Session = Depends(get_db)):
    changes = {k: v for k, v in patch.model_dump(exclude_none=True).items()}
    for key, value in changes.items():
        setattr(settings, key, value)
    audit(db, "settings.updated", f"Updated {', '.join(changes) or 'nothing'}", changes, actor="user")
    return {"updated": changes, **get_settings_endpoint()}


@router.post("/v1/security/kill-switch", tags=["security"], dependencies=[Depends(require_auth)])
def kill_switch(req: KillSwitchRequest, db: Session = Depends(get_db)):
    set_kill_switch(req.enabled, req.reason)
    audit(db, "security.kill_switch", f"Kill switch enabled={req.enabled}", {"reason": req.reason}, actor="user")
    return kill_switch_state()


@router.get("/v1/security/kill-switch", tags=["security"])
def kill_switch_status():
    return kill_switch_state()
