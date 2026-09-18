from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = None
    mode: str = Field(default="auto", pattern="^(auto|local|cloud)$")
    auto_approve: bool = False


class IngestRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class IngestTextRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None


class MemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    kind: str = "fact"
    key: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    meta: dict[str, Any] = Field(default_factory=dict)


class ToolRunRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    auto_approve: bool = False


class ToolToggleRequest(BaseModel):
    enabled: bool


class ApprovalDecision(BaseModel):
    approve: bool
    execute: bool = True


class AutomationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1)
    schedule_seconds: int = Field(default=3600, ge=60, le=86400 * 7)
    enabled: bool = True


class KillSwitchRequest(BaseModel):
    enabled: bool
    reason: str = ""


class SettingsPatch(BaseModel):
    enable_web_search: bool | None = None
    allow_shell_tool: bool | None = None
    allow_browser_tool: bool | None = None
    allow_network_tool: bool | None = None
    local_only: bool | None = None
    cloud_escalation_enabled: bool | None = None
    ollama_model: str | None = None
    openrouter_model: str | None = None
    max_tool_loops: int | None = Field(default=None, ge=1, le=20)


class SkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    trigger_keywords: list[str] | None = None
    status: str = Field(default="active", pattern="^(active|disabled|candidate)$")


class SkillStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled|candidate)$")


class FeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    run_id: str | None = None
    message_id: str | None = None
    comment: str | None = None


class ProvisionRequest(BaseModel):
    model: str | None = None
    include_embeddings: bool = True
