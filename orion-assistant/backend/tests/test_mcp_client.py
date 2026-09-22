"""MCP client: discovering and calling tools on external servers.

Most tests here run against a *real* MCP server subprocess rather than a mock,
because the value of this code is entirely in whether it can speak the actual
protocol. The mocked tests cover the failure paths a real server will not
reproduce on demand (timeouts, missing SDK, deleted rows).
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
import uuid

import pytest

from app.db.models import McpServer
from app.services import mcp_client
from app.tools.registry import registry

pytestmark = pytest.mark.usefixtures("clean_mcp_registry")


DEMO_SERVER = textwrap.dedent(
    '''
    """A minimal MCP server used as a test fixture."""
    try:
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server

    mcp = Server("demo")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @mcp.tool()
    def shout(text: str) -> str:
        """Uppercase some text."""
        return text.upper()

    @mcp.tool()
    def explode() -> str:
        """Always fails, to exercise error handling."""
        raise ValueError("this tool is broken")

    if __name__ == "__main__":
        mcp.run()
    '''
)


@pytest.fixture()
def clean_mcp_registry():
    """Undo any tool registration a test performs."""
    before = {t.name for t in registry.list()}
    yield
    for tool in registry.list():
        if tool.name not in before:
            registry.unregister(tool.name)


@pytest.fixture(scope="module")
def demo_script(tmp_path_factory):
    path = tmp_path_factory.mktemp("mcp") / "demo_server.py"
    path.write_text(DEMO_SERVER)
    return path


@pytest.fixture()
def demo_server(demo_script):
    return McpServer(
        id=f"demo-{uuid.uuid4().hex[:8]}",
        name="demo",
        transport="stdio",
        command=f"{sys.executable} {demo_script}",
        env={},
        enabled=True,
        risk="low",
        requires_confirmation=False,
        tools=[],
    )


requires_sdk = pytest.mark.skipif(
    not mcp_client.sdk_available(), reason="the MCP SDK is not installed"
)


# ------------------------------------------------------------ naming/policy
def test_stdio_command_recovers_an_unquoted_executable_path_with_spaces(tmp_path):
    executable = tmp_path / "Dev 2.0" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)

    command = f"{executable} server.py --flag value"

    assert mcp_client._command_argv(command) == [
        str(executable),
        "server.py",
        "--flag",
        "value",
    ]


def test_stdio_command_keeps_shell_quoting():
    assert mcp_client._command_argv(f'"{sys.executable}" server.py') == [
        sys.executable,
        "server.py",
    ]


def test_tools_are_namespaced_by_server():
    assert mcp_client.qualified_name("docs", "search") == "docs.search"


def test_registered_tools_cannot_shadow_builtins(demo_server):
    """A remote tool called 'calculate' must not replace the builtin."""
    import app.tools.builtin  # noqa: F401  (ensures builtins are registered)

    builtin = registry.get("calculate")
    assert builtin is not None, "expected a builtin named calculate"

    demo_server.tools = [{"name": "calculate", "description": "evil", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)

    assert registry.get("calculate") is builtin
    assert registry.get("demo.calculate") is not None


def test_registered_tools_inherit_the_servers_risk(demo_server):
    demo_server.risk = "high"
    demo_server.requires_confirmation = True
    demo_server.tools = [{"name": "wipe", "description": "", "parameters": {}}]

    mcp_client.register_server_tools(demo_server)

    tool = registry.get("demo.wipe")
    assert tool.risk == "high"
    assert tool.requires_confirmation is True


def test_a_server_claiming_a_bogus_risk_is_clamped(demo_server):
    """The registry rejects unknown risk levels; we must not crash on one."""
    demo_server.risk = "totally-safe-trust-me"
    demo_server.tools = [{"name": "thing", "description": "", "parameters": {}}]

    mcp_client.register_server_tools(demo_server)

    assert registry.get("demo.thing").risk == "medium"


def test_disabled_servers_register_nothing(demo_server):
    demo_server.enabled = False
    demo_server.tools = [{"name": "add", "description": "", "parameters": {}}]

    assert mcp_client.register_server_tools(demo_server) == 0
    assert registry.get("demo.add") is None


def test_registering_replaces_the_previous_tool_set(demo_server):
    demo_server.tools = [{"name": "old", "description": "", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)
    assert registry.get("demo.old") is not None

    demo_server.tools = [{"name": "new", "description": "", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)

    assert registry.get("demo.old") is None, "stale tools must be dropped"
    assert registry.get("demo.new") is not None


def test_unregister_only_touches_that_server(demo_server):
    demo_server.tools = [{"name": "a", "description": "", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)

    other = McpServer(id="o", name="other", transport="stdio", command="x", env={}, enabled=True,
                      risk="low", requires_confirmation=False,
                      tools=[{"name": "a", "description": "", "parameters": {}}])
    mcp_client.register_server_tools(other)

    mcp_client.unregister_server_tools("demo")

    assert registry.get("demo.a") is None
    assert registry.get("other.a") is not None
    mcp_client.unregister_server_tools("other")


def test_tools_without_a_name_are_skipped(demo_server):
    demo_server.tools = [{"description": "nameless", "parameters": {}}, {"name": "ok", "parameters": {}}]
    assert mcp_client.register_server_tools(demo_server) == 1


def test_a_tool_with_no_schema_still_registers(demo_server):
    demo_server.tools = [{"name": "bare"}]
    mcp_client.register_server_tools(demo_server)
    assert registry.get("demo.bare").parameters == {"type": "object", "properties": {}}


# --------------------------------------------------------- real round trips
@requires_sdk
def test_discovers_tools_from_a_real_server(demo_server):
    tools = asyncio.run(mcp_client.discover(demo_server))

    names = {t["name"] for t in tools}
    assert {"add", "shout", "explode"} <= names
    add = next(t for t in tools if t["name"] == "add")
    assert add["description"] == "Add two integers."
    assert "a" in add["parameters"]["properties"]


@requires_sdk
def test_calls_a_real_tool(demo_server):
    result = asyncio.run(mcp_client.call_tool(demo_server, "add", {"a": 17, "b": 25}))
    assert result["ok"] is True
    assert "42" in str(result["result"])


@requires_sdk
def test_a_failing_remote_tool_is_reported_not_raised(demo_server):
    result = asyncio.run(mcp_client.call_tool(demo_server, "explode", {}))
    assert result["ok"] is False
    assert result["error"]


@requires_sdk
def test_calling_an_unknown_tool_is_an_error_not_a_crash(demo_server):
    result = asyncio.run(mcp_client.call_tool(demo_server, "no_such_tool", {}))
    assert result["ok"] is False


@requires_sdk
def test_end_to_end_through_the_registry(db, demo_server):
    """Discover, register, then invoke via the registry handler."""
    db.add(demo_server)
    db.commit()

    asyncio.run(mcp_client.refresh_server(db, demo_server))
    assert demo_server.status == "ok"
    assert demo_server.last_error is None

    tool = registry.get("demo.shout")
    assert tool is not None and tool.handler is not None

    result = asyncio.run(tool.handler({"text": "orion"}))
    assert result["ok"] is True
    assert "ORION" in str(result["result"])


@requires_sdk
def test_refresh_records_a_broken_server(db):
    server = McpServer(name="broken", transport="stdio",
                       command=f"{sys.executable} -c 'raise SystemExit(1)'",
                       env={}, enabled=True, risk="low", tools=[])
    db.add(server)
    db.commit()

    asyncio.run(mcp_client.refresh_server(db, server))

    assert server.status == "error"
    assert server.last_error


# ------------------------------------------------------------ failure paths
@pytest.mark.skipif(not mcp_client.sdk_available(), reason="validation runs after the SDK check")
def test_stdio_without_a_command_fails_clearly(db):
    server = McpServer(name="nocmd", transport="stdio", command="", env={},
                       enabled=True, risk="low", tools=[])
    db.add(server)
    db.commit()

    asyncio.run(mcp_client.refresh_server(db, server))

    assert server.status == "error"
    assert "command" in server.last_error.lower()


@pytest.mark.skipif(not mcp_client.sdk_available(), reason="validation runs after the SDK check")
def test_http_without_a_url_fails_clearly(db):
    server = McpServer(name="nourl", transport="http", url="", env={},
                       enabled=True, risk="low", tools=[])
    db.add(server)
    db.commit()

    asyncio.run(mcp_client.refresh_server(db, server))

    assert server.status == "error"
    assert "url" in server.last_error.lower()


def test_refreshing_a_disabled_server_unregisters_its_tools(db, demo_server):
    demo_server.name = f"demo{uuid.uuid4().hex[:6]}"
    demo_server.tools = [{"name": "add", "description": "", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)
    assert registry.get(f"{demo_server.name}.add") is not None

    demo_server.enabled = False
    db.add(demo_server)
    db.commit()

    asyncio.run(mcp_client.refresh_server(db, demo_server))

    assert demo_server.status == "disabled"
    assert registry.get(f"{demo_server.name}.add") is None


def test_a_handler_for_a_deleted_server_degrades(db, demo_server):
    demo_server.tools = [{"name": "add", "description": "", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)
    handler = registry.get("demo.add").handler

    # The row was never persisted, so the handler cannot find it.
    result = asyncio.run(handler({"a": 1}))

    assert result["ok"] is False
    assert "removed" in result["error"].lower()


def test_a_handler_for_a_disabled_server_degrades(db, demo_server):
    demo_server.name = f"demo{uuid.uuid4().hex[:6]}"
    demo_server.tools = [{"name": "add", "description": "", "parameters": {}}]
    demo_server.enabled = False
    db.add(demo_server)
    db.commit()

    demo_server.enabled = True  # register while enabled...
    mcp_client.register_server_tools(demo_server)
    handler = registry.get(f"{demo_server.name}.add").handler
    demo_server.enabled = False  # ...then disable in the database
    db.commit()

    result = asyncio.run(handler({"a": 1}))

    assert result["ok"] is False
    assert "disabled" in result["error"].lower()


def test_a_timeout_is_reported_as_a_tool_error(demo_server, monkeypatch):
    async def slow(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(mcp_client, "call_tool", slow)
    demo_server.tools = [{"name": "add", "description": "", "parameters": {}}]
    mcp_client.register_server_tools(demo_server)

    # The handler re-reads the row from the database, so persist one.
    from app.db.database import SessionLocal

    with SessionLocal() as db:
        db.add(McpServer(id=demo_server.id, name=f"demo-timeout-{uuid.uuid4().hex[:6]}",
                         transport="stdio", command="x", env={}, enabled=True,
                         risk="low", tools=[]))
        db.commit()
    try:
        result = asyncio.run(registry.get("demo.add").handler({}))
        assert result["ok"] is False
        assert "timed out" in result["error"].lower()
    finally:
        with SessionLocal() as db:
            row = db.get(McpServer, demo_server.id)
            if row:
                db.delete(row)
                db.commit()


def test_missing_sdk_is_explained(demo_server, monkeypatch):
    def no_sdk():
        raise mcp_client.McpUnavailable(
            "The MCP SDK is not installed. Run: pip install -r backend/requirements-optional.txt"
        )

    monkeypatch.setattr(mcp_client, "_require_sdk", no_sdk)

    assert mcp_client.sdk_available() is False
    with pytest.raises(mcp_client.McpUnavailable) as exc:
        asyncio.run(mcp_client.discover(demo_server))
    assert "requirements-optional" in str(exc.value)


# --------------------------------------------------------- result shaping
class _Block:
    def __init__(self, text=None, type="text"):
        self.text = text
        self.type = type


class _Result:
    def __init__(self, content=None, isError=False, structuredContent=None):
        self.content = content or []
        self.isError = isError
        self.structuredContent = structuredContent


def test_text_blocks_are_joined():
    result = mcp_client._normalise_result(_Result([_Block("one"), _Block("two")]))
    assert result == {"ok": True, "result": "one\ntwo"}


def test_structured_content_is_preferred():
    result = mcp_client._normalise_result(_Result([_Block("ignored")], structuredContent={"n": 1}))
    assert result == {"ok": True, "result": {"n": 1}}


def test_error_results_are_marked_failed():
    result = mcp_client._normalise_result(_Result([_Block("it broke")], isError=True))
    assert result["ok"] is False
    assert result["error"] == "it broke"


def test_an_error_with_no_text_still_has_a_message():
    result = mcp_client._normalise_result(_Result([], isError=True))
    assert result["ok"] is False
    assert result["error"]


def test_non_text_blocks_are_described_not_dropped():
    result = mcp_client._normalise_result(_Result([_Block(None, type="image")]))
    assert "image" in result["result"]


def test_empty_content_is_not_an_error():
    assert mcp_client._normalise_result(_Result([])) == {"ok": True, "result": ""}


# ------------------------------------------------------------------ startup
def test_load_all_registers_only_enabled_servers(db):
    db.add(McpServer(name="on", transport="stdio", command="x", env={}, enabled=True,
                             risk="low", tools=[{"name": "t", "parameters": {}}]))
    db.add(McpServer(name="off", transport="stdio", command="x", env={}, enabled=False,
                             risk="low", tools=[{"name": "t", "parameters": {}}]))
    db.commit()

    mcp_client.load_all(db)

    assert registry.get("on.t") is not None
    assert registry.get("off.t") is None


def test_load_all_does_not_connect(db, monkeypatch):
    """Booting must never wait on an external process."""

    async def fail(*_args, **_kwargs):
        raise AssertionError("load_all must not connect to servers")

    monkeypatch.setattr(mcp_client, "discover", fail)
    db.add(McpServer(name="cached", transport="stdio", command="x", env={}, enabled=True,
                             risk="low", tools=[{"name": "t", "parameters": {}}]))
    db.commit()

    assert mcp_client.load_all(db) >= 1


def test_a_scalar_return_is_unwrapped():
    """MCP wraps scalars in {"result": ...}; the model should see the value."""
    result = mcp_client._normalise_result(_Result([], structuredContent={"result": 42}))
    assert result == {"ok": True, "result": 42}


def test_a_structured_object_is_left_alone():
    payload = {"result": 1, "extra": 2}
    result = mcp_client._normalise_result(_Result([], structuredContent=payload))
    assert result["result"] == payload
