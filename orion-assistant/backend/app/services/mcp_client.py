"""MCP client: let ORION use tools hosted by external MCP servers.

ORION ships an MCP *server* (``app.tools.mcp_server``) that exposes a read-only
slice of itself. This module is the mirror image -- the *client* -- which
connects out to other people's MCP servers and folds their tools into the same
registry the builtin tools live in.

Three things matter here:

**Namespacing.** A remote tool ``search`` from a server named ``docs`` is
registered as ``docs.search``. Remote servers can never shadow a builtin, and
the model can tell at a glance where a capability comes from.

**Policy.** Discovered tools inherit the risk level configured on the server
row, and they pass through ``check_tool`` exactly like builtins. A remote
server cannot escalate its own privileges by claiming a tool is harmless.

**Optionality.** The MCP SDK is an optional dependency and remote servers are
frequently unreachable. Nothing in here raises into the agent loop: failures
are captured on the server row and surfaced in the UI, and the assistant simply
carries on without those tools.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import McpServer
from app.tools.registry import ToolDefinition, registry

log = logging.getLogger(__name__)

# Remote calls must not be able to stall the agent loop indefinitely. The
# connect budget includes starting a local stdio process and its MCP handshake;
# cold-starting a Python/Node server can be slow while Ollama is loading a
# model, so keep this separate from the shorter normal call budget.
CONNECT_TIMEOUT = 60.0
CALL_TIMEOUT = 60.0

# Tools from remote servers are tagged so the UI (and the registry) can tell
# them apart from builtins and unregister them cleanly on refresh.
MCP_CATEGORY = "mcp"


class McpUnavailable(RuntimeError):
    """The MCP SDK is not installed."""


def _require_sdk():
    """Import the MCP SDK, or explain how to install it."""
    try:
        from mcp import ClientSession, StdioServerParameters  # noqa: F401
        from mcp.client.stdio import stdio_client  # noqa: F401
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise McpUnavailable(
            "The MCP SDK is not installed. Run: "
            "pip install -r backend/requirements-optional.txt"
        ) from exc
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    return ClientSession, StdioServerParameters, stdio_client


def sdk_available() -> bool:
    try:
        _require_sdk()
        return True
    except McpUnavailable:
        return False


def qualified_name(server_name: str, tool_name: str) -> str:
    """``docs`` + ``search`` -> ``docs.search``."""
    return f"{server_name}.{tool_name}"


# --------------------------------------------------------------- connection


def _is_executable_file(path: str) -> bool:
    """Return whether *path* names a runnable file.

    ``shlex.split`` is intentionally used for MCP commands so that shell
    metacharacters are never interpreted.  A command assembled by a caller can
    nevertheless contain an unquoted executable path with spaces (for example,
    a virtualenv below ``/opt/Dev 2.0``).  In that case ``shlex.split`` turns
    one path into several tokens and the MCP SDK tries to execute the first
    directory.  Keep this small check separate from ``shutil.which`` because
    ``which`` is allowed to resolve names on PATH, while this helper must not
    treat a directory as an executable merely because it has search permission.
    """
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _command_argv(command: str) -> list[str]:
    """Parse a stdio command without invoking a shell.

    Normal commands follow shell-style quoting, e.g. ``python server.py`` or
    ``"/path with spaces/python" server.py``.  For compatibility with commands
    assembled programmatically, also recover an *unquoted* executable path with
    spaces when its first token is not runnable.  Only the leading executable
    is reassembled; all remaining tokens stay arguments and shell expansion is
    never performed.
    """
    argv = shlex.split(command or "")
    if not argv:
        return []

    # A normal absolute/relative path or a command available on PATH needs no
    # special handling.  ``shutil.which`` also covers commands such as ``npx``.
    if _is_executable_file(argv[0]) or shutil.which(argv[0]):
        return argv

    # The path was split at spaces.  Look for the first prefix that is a real
    # executable file, rather than accepting a directory with execute/search
    # permission as the command.
    for end in range(2, len(argv) + 1):
        candidate = " ".join(argv[:end])
        if _is_executable_file(candidate):
            return [candidate, *argv[end:]]

    # Let the SDK produce its usual useful OS error for an actually missing
    # command.  This also preserves PATH lookup semantics for unusual command
    # names that were not found locally.
    return argv


class _Connection:
    """A short-lived MCP session.

    Sessions are opened per operation rather than held open. Long-lived stdio
    subprocesses are a reliability and resource problem for a local-first app
    that may sit idle for hours, and MCP handshakes are cheap.
    """

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self._stack: AsyncExitStack | None = None
        self.session: Any = None

    async def __aenter__(self):
        ClientSession, StdioServerParameters, stdio_client = _require_sdk()
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        try:
            if self.server.transport == "http":
                if not self.server.url:
                    raise ValueError("HTTP transport requires a url")

                import mcp.client.streamable_http as http_transport

                # Renamed between SDK majors.
                streamablehttp_client = getattr(
                    http_transport, "streamable_http_client", None
                ) or http_transport.streamablehttp_client
                read, write, *_ = await self._stack.enter_async_context(
                    streamablehttp_client(self.server.url)
                )
            else:
                argv = _command_argv(self.server.command or "")
                if not argv:
                    raise ValueError("stdio transport requires a command")
                params = StdioServerParameters(
                    command=argv[0],
                    args=argv[1:],
                    env=dict(self.server.env or {}) or None,
                )
                read, write = await self._stack.enter_async_context(stdio_client(params))

            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(self.session.initialize(), timeout=CONNECT_TIMEOUT)
            return self
        except BaseException:
            await self._stack.aclose()
            self._stack = None
            raise

    async def __aexit__(self, *exc_info):
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        return False


# ---------------------------------------------------------------- discovery


def _tool_summary(tool: Any) -> dict[str, Any]:
    """Normalise an SDK tool object into plain JSON for storage."""
    # 1.x used camelCase; 2.x renamed these to snake_case.
    schema = (
        getattr(tool, "input_schema", None)
        or getattr(tool, "inputSchema", None)
        or {"type": "object", "properties": {}}
    )
    return {
        "name": getattr(tool, "name", ""),
        "description": (getattr(tool, "description", "") or "").strip(),
        "parameters": schema,
    }


async def discover(server: McpServer) -> list[dict[str, Any]]:
    """Connect to a server and return its tool list.

    Raises on failure -- callers that persist state should use
    :func:`refresh_server`, which records the error instead.
    """
    async with _Connection(server) as connection:
        result = await asyncio.wait_for(connection.session.list_tools(), timeout=CONNECT_TIMEOUT)
        return [_tool_summary(tool) for tool in getattr(result, "tools", [])]


async def call_tool(server: McpServer, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke a single tool on a remote server and normalise the result."""
    async with _Connection(server) as connection:
        result = await asyncio.wait_for(
            connection.session.call_tool(tool_name, arguments or {}),
            timeout=CALL_TIMEOUT,
        )
    return _normalise_result(result)


def _normalise_result(result: Any) -> dict[str, Any]:
    """Flatten MCP's content blocks into the shape ORION's tools return.

    MCP replies are a list of typed content blocks; the agent loop wants text
    it can put in a tool message. Text blocks are joined, and anything
    non-text is described rather than dropped silently.
    """
    if getattr(result, "is_error", False) or getattr(result, "isError", False):
        return {"ok": False, "error": _content_text(result) or "The MCP tool reported an error"}

    structured = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if structured:
        # The SDK wraps a scalar return value in {"result": ...}; unwrap it so
        # the model sees `42` rather than `{"result": {"result": 42}}`.
        if isinstance(structured, dict) and set(structured) == {"result"}:
            structured = structured["result"]
        return {"ok": True, "result": structured}

    return {"ok": True, "result": _content_text(result)}


def _content_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        else:
            kind = getattr(block, "type", "content")
            parts.append(f"[{kind} omitted]")
    return "\n".join(parts).strip()


# ----------------------------------------------------------- registry sync


def _make_handler(server_id: str, remote_name: str):
    """Build a registry handler bound to a server row.

    The row is re-read per call rather than captured, so edits to the server's
    command or URL take effect without re-registering the tool.
    """

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from app.db.database import SessionLocal

        with SessionLocal() as db:
            server = db.get(McpServer, server_id)
            if server is None:
                return {"ok": False, "error": "This MCP server has been removed"}
            if not server.enabled:
                return {"ok": False, "error": f"The MCP server '{server.name}' is disabled"}
            detached = _detach(server)

        try:
            return await call_tool(detached, remote_name, args)
        except McpUnavailable as exc:
            return {"ok": False, "error": str(exc)}
        except TimeoutError:
            return {"ok": False, "error": f"The MCP server '{detached.name}' timed out"}
        except Exception as exc:  # noqa: BLE001 - never break the agent loop
            log.warning("MCP call %s.%s failed: %s", detached.name, remote_name, exc)
            return {"ok": False, "error": f"MCP call failed: {exc}"}

    return handler


def _detach(server: McpServer) -> McpServer:
    """Copy the fields a connection needs, free of the ORM session."""
    copy = McpServer(
        id=server.id,
        name=server.name,
        transport=server.transport,
        command=server.command,
        url=server.url,
        env=dict(server.env or {}),
        enabled=server.enabled,
        risk=server.risk,
        requires_confirmation=server.requires_confirmation,
    )
    return copy


def unregister_server_tools(server_name: str) -> int:
    """Remove every registered tool belonging to a server."""
    prefix = f"{server_name}."
    names = [t.name for t in registry.list() if t.category == MCP_CATEGORY and t.name.startswith(prefix)]
    for name in names:
        registry.unregister(name)
    return len(names)


def register_server_tools(server: McpServer) -> int:
    """Register a server's discovered tools, replacing any previous set."""
    unregister_server_tools(server.name)
    if not server.enabled:
        return 0

    count = 0
    for tool in server.tools or []:
        remote_name = tool.get("name")
        if not remote_name:
            continue
        registry.register(
            ToolDefinition(
                name=qualified_name(server.name, remote_name),
                description=(tool.get("description") or f"{remote_name} (via {server.name})"),
                parameters=tool.get("parameters") or {"type": "object", "properties": {}},
                risk=server.risk if server.risk in ("low", "medium", "high", "destructive") else "medium",
                requires_confirmation=server.requires_confirmation,
                handler=_make_handler(server.id, remote_name),
                category=MCP_CATEGORY,
                tags=["mcp", server.name],
            )
        )
        count += 1
    return count


async def refresh_server(db: Session, server: McpServer) -> McpServer:
    """Reconnect, re-discover tools, and record the outcome on the row."""
    if not server.enabled:
        server.status = "disabled"
        server.last_error = None
        unregister_server_tools(server.name)
        db.commit()
        db.refresh(server)
        return server

    try:
        tools = await discover(_detach(server))
    except McpUnavailable as exc:
        server.status = "error"
        server.last_error = str(exc)
    except TimeoutError:
        server.status = "error"
        server.last_error = f"Timed out after {CONNECT_TIMEOUT:.0f}s while connecting"
    except Exception as exc:  # noqa: BLE001 - a bad server must not break the app
        server.status = "error"
        server.last_error = str(exc)
        log.warning("MCP discovery failed for %s: %s", server.name, exc)
    else:
        server.tools = tools
        server.status = "ok"
        server.last_error = None
        server.last_connected_at = datetime.now(UTC)

    db.commit()
    db.refresh(server)
    register_server_tools(server)
    return server


def load_all(db: Session) -> int:
    """Register tools for every enabled server from their cached discovery.

    Called at startup: it uses the last known tool list rather than connecting,
    so booting ORION never waits on external processes. A server is refreshed
    when the user asks, or on first failed call.
    """
    total = 0
    for server in db.query(McpServer).filter(McpServer.enabled.is_(True)).all():
        total += register_server_tools(server)
    return total


async def refresh_all(db: Session) -> dict[str, Any]:
    """Refresh every enabled server, reporting per-server outcomes."""
    results = []
    for server in db.query(McpServer).filter(McpServer.enabled.is_(True)).all():
        await refresh_server(db, server)
        results.append(
            {
                "name": server.name,
                "status": server.status,
                "tools": len(server.tools or []),
                "error": server.last_error,
            }
        )
    return {"servers": results, "sdk_available": sdk_available()}
