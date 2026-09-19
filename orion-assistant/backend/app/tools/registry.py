from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

RISK_LEVELS = ("low", "medium", "high", "destructive")


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str = "low"
    requires_confirmation: bool = False
    handler: ToolFn | None = None
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    enabled: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.risk not in RISK_LEVELS:
            raise ValueError(f"Invalid risk level: {tool.risk}")
        self._tools[tool.name] = tool
        return tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def list(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda t: (t.category, t.name))

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        tool = self._tools.get(name)
        if not tool:
            return False
        tool.enabled = enabled
        return True

    def openai_schemas(self, only_allowed: bool = True) -> list[dict[str, Any]]:
        from app.core.policy import check_tool

        schemas = []
        for tool in self._tools.values():
            if only_allowed:
                decision = check_tool(tool)
                if not decision.allowed:
                    continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    def as_dicts(self) -> list[dict[str, Any]]:
        from app.core.policy import check_tool

        out = []
        for tool in self.list():
            decision = check_tool(tool)
            out.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "risk": tool.risk,
                    "category": tool.category,
                    "tags": tool.tags,
                    "enabled": tool.enabled,
                    "requires_confirmation": tool.requires_confirmation or decision.approval_required,
                    "allowed": decision.allowed,
                    "policy_reason": decision.reason,
                    "parameters": tool.parameters,
                }
            )
        return out


registry = ToolRegistry()
