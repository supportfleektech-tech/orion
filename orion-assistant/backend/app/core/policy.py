from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.tools.registry import ToolDefinition

KILL_SWITCH = {"enabled": False, "reason": ""}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    approval_required: bool
    reason: str


def set_kill_switch(enabled: bool, reason: str = "") -> None:
    KILL_SWITCH["enabled"] = enabled
    KILL_SWITCH["reason"] = reason


def kill_switch_state() -> dict:
    return dict(KILL_SWITCH)


def check_tool(tool: ToolDefinition) -> Decision:
    if KILL_SWITCH["enabled"]:
        return Decision(False, False, f"Kill switch engaged: {KILL_SWITCH['reason'] or 'all tools halted'}")
    if not tool.enabled:
        return Decision(False, False, "Tool disabled by operator")
    if tool.name == "web_search" and not settings.enable_web_search:
        return Decision(False, False, "Web search is disabled by configuration")
    if tool.category == "shell" and not settings.allow_shell_tool:
        return Decision(False, False, "Shell execution is disabled by configuration")
    if tool.category == "browser" and not settings.allow_browser_tool:
        return Decision(False, False, "Browser automation is disabled by configuration")
    if tool.category == "network" and not settings.allow_network_tool:
        return Decision(False, False, "Network tooling is disabled by configuration")
    if tool.risk in {"high", "destructive"} or tool.requires_confirmation:
        return Decision(True, True, "Explicit approval required by risk policy")
    return Decision(True, False, "Allowed by local policy")
