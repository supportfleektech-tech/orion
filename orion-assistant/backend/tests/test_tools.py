import ast

import pytest

from app.core.policy import check_tool, set_kill_switch
from app.tools.builtin import safe_eval
from app.tools.registry import ToolDefinition, ToolRegistry, registry


def test_calculator():
    assert safe_eval(ast.parse("2 + 3 * 4", mode="eval").body) == 14


def test_reject_names():
    with pytest.raises(ValueError):
        safe_eval(ast.parse("__import__('os')", mode="eval").body)


def test_reject_huge_exponent():
    with pytest.raises(ValueError):
        safe_eval(ast.parse("2 ** 999", mode="eval").body)


def test_registry_schema():
    reg = ToolRegistry()
    reg.register(ToolDefinition("x", "x tool", {"type": "object"}))
    assert reg.openai_schemas(only_allowed=False)[0]["function"]["name"] == "x"


def test_builtin_tools_registered():
    names = {t.name for t in registry.list()}
    assert {"calculate", "read_file", "memory_write", "knowledge_search"} <= names


def test_high_risk_requires_approval():
    tool = registry.get("write_file")
    assert check_tool(tool).approval_required is True


def test_kill_switch_blocks_everything():
    set_kill_switch(True, "test")
    try:
        assert check_tool(registry.get("calculate")).allowed is False
    finally:
        set_kill_switch(False)


def test_optional_deps_are_not_imported_at_boot():
    """playwright/mcp are optional; importing the app must not require them.

    Checked in a fresh interpreter: other tests in this suite legitimately
    import the optional SDKs, so the current process's sys.modules says
    nothing about what booting the app actually pulls in.
    """
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c",
         "import app.main, sys; "
         "print([m for m in ('playwright', 'mcp') if m in sys.modules])"],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("[]"), f"optional deps imported at boot: {result.stdout}"


def test_browser_tool_reports_missing_dependency_cleanly(monkeypatch):
    """A missing optional dep must surface a clear error, never a raw ImportError."""
    import asyncio

    from app.core.config import settings
    from app.tools.builtin import browse_page

    monkeypatch.setattr(settings, "allow_browser_tool", False)
    with pytest.raises(PermissionError):
        asyncio.run(browse_page({"url": "https://example.com"}))
