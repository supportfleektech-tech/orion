from __future__ import annotations

import ast
import operator
from pathlib import Path
import httpx
from app.core.config import settings
from app.tools.registry import ToolDefinition, registry


OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](safe_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](safe_eval(node.left), safe_eval(node.right))
    raise ValueError("Unsupported expression")


async def calculate(args: dict) -> dict:
    expr = str(args["expression"]).strip()
    if len(expr) > 200:
        raise ValueError("Expression too long")
    return {"expression": expr, "result": safe_eval(ast.parse(expr, mode="eval").body)}


async def list_files(args: dict) -> dict:
    base = Path("knowledge").resolve()
    root = (base / args.get("path", ".")).resolve()
    if base not in root.parents and root != base:
        raise PermissionError("Path escapes knowledge directory")
    if not root.exists():
        return {"files": []}
    files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()][:200]
    return {"root": str(root), "files": files}


async def read_file(args: dict) -> dict:
    root = Path("knowledge").resolve()
    target = (root / args["path"]).resolve()
    if root not in target.parents and target != root:
        raise PermissionError("Path escapes knowledge directory")
    if not target.is_file():
        raise FileNotFoundError(args["path"])
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"path": args["path"], "content": text[:20000]}


async def web_search(args: dict) -> dict:
    if not settings.enable_web_search:
        raise PermissionError("Web search is disabled")
    q = str(args["query"])
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{settings.searxng_base_url}/search", params={"q": q, "format": "json"})
        r.raise_for_status()
        data = r.json()
    return {"query": q, "results": data.get("results", [])[:10]}


registry.register(ToolDefinition(
    name="calculate",
    description="Safely evaluate a basic arithmetic expression.",
    parameters={"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]},
    risk="low",
    handler=calculate,
))
registry.register(ToolDefinition(
    name="list_files",
    description="List files in ORION's knowledge directory.",
    parameters={"type":"object","properties":{"path":{"type":"string","default":"."}}},
    risk="low",
    handler=list_files,
))
registry.register(ToolDefinition(
    name="read_file",
    description="Read a file from ORION's knowledge directory.",
    parameters={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]},
    risk="low",
    handler=read_file,
))
registry.register(ToolDefinition(
    name="web_search",
    description="Search the web using a configured SearXNG instance.",
    parameters={"type":"object","properties":{"query":{"type":"string"}},"required":["query"]},
    risk="medium",
    requires_confirmation=False,
    handler=web_search,
))
