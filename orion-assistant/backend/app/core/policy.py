from __future__ import annotations

from dataclasses import dataclass
from app.core.config import settings
from app.tools.registry import ToolDefinition


@dataclass(frozen=True)
class Decision:
    allowed: bool
    approval_required: bool
    reason: str


def check_tool(tool: ToolDefinition) -> Decision:
    if tool.name in {"web_search"} and not settings.enable_web_search:
        return Decision(False, False, "Web search is disabled by configuration")
    if tool.name.startswith("shell_") and not settings.allow_shell_tool:
        return Decision(False, False, "Shell execution is disabled by configuration")
    if tool.name.startswith("browser_") and not settings.allow_browser_tool:
        return Decision(False, False, "Browser automation is disabled by configuration")
    if tool.name.startswith("network_") and not settings.allow_network_tool:
        return Decision(False, False, "Network tooling is disabled by configuration")
    if tool.risk in {"high", "destructive"} or tool.requires_confirmation:
        return Decision(True, True, "Explicit approval required by risk policy")
    return Decision(True, False, "Allowed by local policy")
