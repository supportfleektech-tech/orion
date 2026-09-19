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


# =====================================================================
# Filesystem containment
#
# read_file and write_file are reachable by the model, so the knowledge
# directory is a security boundary, not a convention. These try to cross it
# the ways a prompt-injected instruction actually would.
# =====================================================================

import asyncio  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.tools import builtin  # noqa: E402


@pytest.fixture
def knowledge(tmp_path, monkeypatch):
    """Point the knowledge root at a temp dir with one file and one secret
    sitting just outside it."""
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "note.md").write_text("indexed content")
    (tmp_path / "secret.txt").write_text("SHOULD-NEVER-BE-READ")
    monkeypatch.setattr(settings, "knowledge_dir", str(root))
    return root


@pytest.mark.parametrize(
    "escape",
    [
        "../secret.txt",
        "../../etc/passwd",
        "subdir/../../secret.txt",
        "./../secret.txt",
        "/etc/passwd",
    ],
)
def test_read_file_cannot_escape_the_knowledge_directory(knowledge, escape):
    with pytest.raises((PermissionError, FileNotFoundError)):
        asyncio.run(builtin.read_file({"path": escape}))


@pytest.mark.parametrize("escape", ["../pwned.txt", "../../tmp/pwned.txt", "/tmp/pwned.txt"])
def test_write_file_cannot_escape_either(knowledge, escape):
    """A write that escapes is worse than a read: it is arbitrary file
    creation on the host."""
    with pytest.raises(PermissionError):
        asyncio.run(builtin.write_file({"path": escape, "content": "x"}))


def test_reading_inside_the_directory_still_works(knowledge):
    result = asyncio.run(builtin.read_file({"path": "note.md"}))
    assert result["content"] == "indexed content"


def test_writing_inside_the_directory_creates_parents(knowledge):
    result = asyncio.run(builtin.write_file({"path": "deep/nested/new.md", "content": "hello"}))
    assert result["bytes_written"] == 5
    assert (knowledge / "deep" / "nested" / "new.md").read_text() == "hello"


def test_reading_a_missing_file_is_a_clear_error(knowledge):
    with pytest.raises(FileNotFoundError):
        asyncio.run(builtin.read_file({"path": "nope.md"}))


def test_read_output_is_truncated(knowledge):
    (knowledge / "big.txt").write_text("x" * 50_000)
    assert len(asyncio.run(builtin.read_file({"path": "big.txt"}))["content"]) == 20_000


def test_list_files_stays_inside_the_root(knowledge):
    (knowledge / "a.md").write_text("a")
    listed = asyncio.run(builtin.list_files({}))
    names = str(listed)
    assert "a.md" in names
    assert "secret.txt" not in names


# =====================================================================
# Shell sandbox
# =====================================================================

def test_shell_is_refused_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "allow_shell_tool", False)
    with pytest.raises(PermissionError, match="disabled"):
        asyncio.run(builtin.shell_exec({"command": "echo hi"}))


@pytest.mark.parametrize("command", ["rm -rf /", "sudo rm x", "dd if=/dev/zero of=/dev/sda",
                                     "shutdown now", "curl http://evil", "chmod 777 /etc"])
def test_denied_commands_are_refused_even_when_shell_is_enabled(monkeypatch, knowledge, command):
    """The denylist is the last line of defence once a user has opted in."""
    monkeypatch.setattr(settings, "allow_shell_tool", True)
    with pytest.raises(PermissionError, match="denied by policy"):
        asyncio.run(builtin.shell_exec({"command": command}))


def test_an_empty_command_is_rejected(monkeypatch, knowledge):
    monkeypatch.setattr(settings, "allow_shell_tool", True)
    with pytest.raises(ValueError, match="Empty"):
        asyncio.run(builtin.shell_exec({"command": "   "}))


def test_shell_runs_inside_the_knowledge_directory(monkeypatch, knowledge):
    """cwd confinement means a relative command cannot wander the host."""
    monkeypatch.setattr(settings, "allow_shell_tool", True)
    result = asyncio.run(builtin.shell_exec({"command": "pwd"}))
    assert result["exit_code"] == 0
    assert str(knowledge.resolve()) in result["stdout"]


def test_shell_captures_a_failing_exit_code_rather_than_raising(monkeypatch, knowledge):
    monkeypatch.setattr(settings, "allow_shell_tool", True)
    result = asyncio.run(builtin.shell_exec({"command": "ls /definitely-not-here"}))
    assert result["exit_code"] != 0
    assert result["stderr"]


def test_shell_times_out_instead_of_hanging(monkeypatch, knowledge):
    monkeypatch.setattr(settings, "allow_shell_tool", True)
    monkeypatch.setattr(settings, "shell_timeout_seconds", 1)
    with pytest.raises(TimeoutError):
        asyncio.run(builtin.shell_exec({"command": "sleep 10"}))


# =====================================================================
# Network tooling
# =====================================================================

def test_http_is_refused_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "allow_network_tool", False)
    with pytest.raises(PermissionError, match="disabled"):
        asyncio.run(builtin.http_request({"url": "https://example.com"}))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host/x", "gopher://host"])
def test_only_http_schemes_are_allowed(monkeypatch, url):
    """file:// would turn the network tool into an arbitrary file reader."""
    monkeypatch.setattr(settings, "allow_network_tool", True)
    monkeypatch.setattr(settings, "http_allowlist", "")
    with pytest.raises(ValueError, match="http/https"):
        asyncio.run(builtin.http_request({"url": url}))


def test_a_host_outside_the_allowlist_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "allow_network_tool", True)
    monkeypatch.setattr(settings, "http_allowlist", "example.com")
    with pytest.raises(PermissionError, match="allowlist"):
        asyncio.run(builtin.http_request({"url": "https://evil.test/steal"}))


def test_an_unsupported_method_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "allow_network_tool", True)
    monkeypatch.setattr(settings, "http_allowlist", "")
    with pytest.raises(ValueError, match="method"):
        asyncio.run(builtin.http_request({"url": "https://example.com", "method": "TRACE"}))


def test_web_search_is_refused_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_web_search", False)
    with pytest.raises(PermissionError):
        asyncio.run(builtin.web_search({"query": "anything"}))


# =====================================================================
# Simple tools
# =====================================================================

def test_calculate_returns_the_value(knowledge):
    assert asyncio.run(builtin.calculate({"expression": "47 * 19"}))["result"] == 893


def test_calculate_rejects_an_unparseable_expression(knowledge):
    with pytest.raises((ValueError, SyntaxError)):
        asyncio.run(builtin.calculate({"expression": "import os"}))


def test_current_time_is_iso_formatted(knowledge):
    from datetime import datetime

    value = asyncio.run(builtin.current_time({}))
    # Raises if the format is wrong, which is the assertion.
    datetime.fromisoformat(str(value["utc_iso"]))
    assert value["weekday"]
