from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = Field(default=None, max_length=64)
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
    persona: str | None = Field(default=None, max_length=60)
    system_prompt: str | None = Field(default=None, max_length=8000)


class MemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    kind: str = Field(default="fact", max_length=40)
    key: str | None = Field(default=None, max_length=200)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    meta: dict[str, Any] = Field(default_factory=dict)


class ToolRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    auto_approve: bool = False


class ToolToggleRequest(BaseModel):
    enabled: bool


class ApprovalDecision(BaseModel):
    approve: bool
    execute: bool = True


class AutomationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Becomes the agent's task on every scheduled run; matches the chat limit.
    prompt: str = Field(min_length=1, max_length=20000)
    schedule_seconds: int = Field(default=3600, ge=60, le=86400 * 7)
    enabled: bool = True


class KillSwitchRequest(BaseModel):
    enabled: bool
    reason: str = Field(default="", max_length=500)


class SettingsPatch(BaseModel):
    enable_web_search: bool | None = None
    allow_shell_tool: bool | None = None
    allow_browser_tool: bool | None = None
    allow_network_tool: bool | None = None
    local_only: bool | None = None
    cloud_escalation_enabled: bool | None = None
    ollama_model: str | None = Field(default=None, max_length=200)
    openrouter_model: str | None = Field(default=None, max_length=200)
    max_tool_loops: int | None = Field(default=None, ge=1, le=20)


class SkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Rendered into the system prompt next to the instructions, so it needs a
    # ceiling for the same reason they do.
    description: str = Field(min_length=1, max_length=2000)
    instructions: str = Field(min_length=1, max_length=8000)
    trigger_keywords: list[str] | None = None
    status: str = Field(default="active", pattern="^(active|disabled|candidate)$")


class SkillStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled|candidate)$")


class FeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    run_id: str | None = Field(default=None, max_length=64)
    message_id: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=4000)


class ProvisionRequest(BaseModel):
    model: str | None = Field(default=None, max_length=200)
    include_embeddings: bool = True


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice: str | None = Field(default=None, max_length=40)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


class VoiceCommandRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=2000)
    require_wake_word: bool | None = None


class McpServerRequest(BaseModel):
    """Register an external MCP server whose tools ORION may call."""

    name: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(default="", max_length=1000)
    transport: str = Field(default="stdio", pattern="^(stdio|http)$")
    command: str = Field(default="", max_length=2000)
    url: str = Field(default="", max_length=2000)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    risk: str = Field(default="medium", pattern="^(low|medium|high|destructive)$")
    requires_confirmation: bool = True


class McpServerPatch(BaseModel):
    description: str | None = Field(default=None, max_length=1000)
    transport: str | None = Field(default=None, pattern="^(stdio|http)$")
    command: str | None = Field(default=None, max_length=2000)
    url: str | None = Field(default=None, max_length=2000)
    env: dict[str, str] | None = None
    enabled: bool | None = None
    risk: str | None = Field(default=None, pattern="^(low|medium|high|destructive)$")
    requires_confirmation: bool | None = None
