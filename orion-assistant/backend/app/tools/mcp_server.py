"""Minimal MCP server exposing a safe ORION capability.

Run with an installed MCP SDK. This example is deliberately read-only.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("orion-safe-tools")


@mcp.tool()
def ping(message: str = "pong") -> str:
    """Return a health response without modifying state."""
    return f"ORION MCP: {message}"


if __name__ == "__main__":
    mcp.run()
