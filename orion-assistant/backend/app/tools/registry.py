from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str = "low"  # low | medium | high | destructive
    requires_confirmation: bool = False
    handler: ToolFn | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]


registry = ToolRegistry()
