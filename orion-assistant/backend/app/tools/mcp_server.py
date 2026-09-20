"""Optional MCP server exposing a safe, read-only subset of ORION.

This is an *optional* integration surface, not part of the API service. It lets
MCP-compatible clients (editors, desktop assistants) query ORION's memory and
knowledge without granting any write or side-effecting capability.

The MCP SDK is not a required dependency. Install it explicitly:

    pip install "mcp>=1.10"
    python -m app.tools.mcp_server

Only low-risk read tools are exposed here by design. Anything that writes,
spends, sends or deletes must go through the HTTP API's policy gate and
approval queue instead.
"""

from __future__ import annotations

import asyncio
import sys

# The SDK renamed FastMCP to MCPServer in 2.0. Support both so this works
# whichever major version the user has installed.
try:
    from mcp.server.mcpserver import MCPServer as _Server  # mcp >= 2
except ImportError:  # pragma: no cover - depends on installed version
    try:
        from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x
    except ImportError:  # pragma: no cover - optional dependency
        print(
            'The MCP SDK is not installed. Run:  pip install "mcp>=1.10"',
            file=sys.stderr,
        )
        raise SystemExit(1) from None

from app.db.database import SessionLocal, init_db
from app.services.ingestion import search_chunks
from app.services.memory import retrieve_memories

mcp = _Server("orion-safe-tools")


@mcp.tool()
def ping(message: str = "pong") -> str:
    """Return a health response without modifying state."""
    return f"ORION MCP: {message}"


@mcp.tool()
def search_memory(query: str, limit: int = 5) -> list[dict]:
    """Search ORION's long-term memory. Read-only."""
    db = SessionLocal()
    try:
        return asyncio.run(retrieve_memories(db, query, limit))
    finally:
        db.close()


@mcp.tool()
def search_knowledge(query: str, limit: int = 5) -> list[dict]:
    """Semantic search over ORION's ingested documents. Read-only."""
    db = SessionLocal()
    try:
        return asyncio.run(search_chunks(db, query, limit))
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    mcp.run()
