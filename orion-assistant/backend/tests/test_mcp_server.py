"""The optional MCP server: ORION exposed to other tools, read-only.

This is a separate process, not part of the API service, so it is exercised
the way it actually runs -- imported and driven in a subprocess -- rather than
by poking at module internals. Importing it in-process would construct a
server and register global handlers, which then leak into other tests.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

pytest.importorskip("mcp", reason="the MCP SDK is an optional extra")


def run(code: str) -> subprocess.CompletedProcess:
    """Execute a snippet in a fresh interpreter with the backend importable."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=90,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": "sqlite:///:memory:",
             "PYTHONPATH": str(BACKEND), "HOME": "/tmp"},
    )


def test_the_module_imports_and_builds_a_server():
    result = run("""
        from app.tools import mcp_server
        assert mcp_server.mcp is not None
        print("OK")
    """)
    assert "OK" in result.stdout, result.stderr


def test_it_exposes_exactly_the_three_read_only_tools():
    """Adding a write tool here would bypass the policy gate and approval
    queue entirely, so the surface is asserted explicitly."""
    result = run("""
        import asyncio
        from app.tools import mcp_server

        tools = asyncio.run(mcp_server.mcp.list_tools())
        print(sorted(t.name for t in tools))
    """)
    assert result.returncode == 0, result.stderr
    assert "['ping', 'search_knowledge', 'search_memory']" in result.stdout


def test_every_exposed_tool_is_documented():
    result = run("""
        import asyncio
        from app.tools import mcp_server

        tools = asyncio.run(mcp_server.mcp.list_tools())
        missing = [t.name for t in tools if not (t.description or "").strip()]
        print("MISSING", missing)
    """)
    assert "MISSING []" in result.stdout, result.stderr


def test_ping_answers_without_touching_the_database():
    result = run("""
        from app.tools import mcp_server
        print(mcp_server.ping("hello"))
    """)
    assert "ORION MCP: hello" in result.stdout, result.stderr


def test_searching_an_empty_database_returns_nothing_rather_than_failing():
    result = run("""
        from app.db.database import init_db
        from app.tools import mcp_server

        init_db()
        print("MEM", mcp_server.search_memory("anything"))
        print("DOC", mcp_server.search_knowledge("anything"))
    """)
    assert result.returncode == 0, result.stderr
    assert "MEM []" in result.stdout
    assert "DOC []" in result.stdout


def test_stored_memory_is_findable_through_the_server():
    """The read path has to actually work, not just not crash."""
    result = run("""
        import asyncio
        from app.db.database import SessionLocal, init_db
        from app.services.memory import write_memory
        from app.tools import mcp_server

        init_db()
        db = SessionLocal()
        asyncio.run(write_memory(db, "The deploy key lives in the vault.",
                                 kind="fact", key="deploy"))
        db.commit()
        db.close()

        hits = mcp_server.search_memory("deploy key")
        print("FOUND", any("vault" in str(h.get("content", "")) for h in hits))
    """)
    assert "FOUND True" in result.stdout, result.stderr


def test_it_exits_with_a_clear_message_when_the_sdk_is_absent():
    """The module is opt-in, so a missing SDK must explain itself rather than
    raising ImportError at the user."""
    result = run("""
        import builtins, sys

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.startswith("mcp"):
                raise ImportError("no mcp")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = blocked
        for mod in [m for m in sys.modules if m.startswith("mcp")]:
            del sys.modules[mod]

        try:
            from app.tools import mcp_server  # noqa: F401
        except SystemExit as exc:
            print("EXITED", exc.code)
    """)
    assert "EXITED 1" in result.stdout, result.stderr
    assert "pip install" in result.stderr
