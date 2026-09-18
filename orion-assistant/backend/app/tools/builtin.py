from __future__ import annotations

import ast
import asyncio
import json
import operator
import shlex
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.tools.registry import ToolDefinition, registry

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](safe_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        if isinstance(node.op, ast.Pow):
            exponent = safe_eval(node.right)
            if abs(exponent) > 64:
                raise ValueError("Exponent too large")
            return OPS[ast.Pow](safe_eval(node.left), exponent)
        return OPS[type(node.op)](safe_eval(node.left), safe_eval(node.right))
    raise ValueError("Unsupported expression")


def _knowledge_root() -> Path:
    root = Path(settings.knowledge_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_in_knowledge(rel: str) -> Path:
    root = _knowledge_root()
    target = (root / (rel or ".")).resolve()
    if target != root and root not in target.parents:
        raise PermissionError("Path escapes the knowledge directory")
    return target


async def calculate(args: dict) -> dict:
    expr = str(args.get("expression", "")).strip()
    if not expr:
        raise ValueError("expression is required")
    if len(expr) > 200:
        raise ValueError("Expression too long")
    return {"expression": expr, "result": safe_eval(ast.parse(expr, mode="eval").body)}


async def current_time(args: dict) -> dict:
    now = datetime.now(UTC)
    return {"utc_iso": now.isoformat(), "unix": int(now.timestamp()), "weekday": now.strftime("%A")}


async def list_files(args: dict) -> dict:
    root = _resolve_in_knowledge(str(args.get("path", ".")))
    if not root.exists():
        return {"root": str(root), "files": []}
    if root.is_file():
        return {"root": str(root.parent), "files": [root.name]}
    files = [str(p.relative_to(root)) for p in sorted(root.rglob("*")) if p.is_file()][:300]
    return {"root": str(root), "files": files}


async def read_file(args: dict) -> dict:
    target = _resolve_in_knowledge(str(args["path"]))
    if not target.is_file():
        raise FileNotFoundError(str(args["path"]))
    return {"path": str(args["path"]), "content": target.read_text(encoding="utf-8", errors="replace")[:20000]}


async def write_file(args: dict) -> dict:
    target = _resolve_in_knowledge(str(args["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    content = str(args.get("content", ""))
    target.write_text(content, encoding="utf-8")
    return {"path": str(args["path"]), "bytes_written": len(content.encode("utf-8"))}


async def web_search(args: dict) -> dict:
    if not settings.enable_web_search:
        raise PermissionError("Web search is disabled")
    query = str(args["query"])
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(
            f"{settings.searxng_base_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
        )
        r.raise_for_status()
        data = r.json()
    results = [
        {"title": x.get("title"), "url": x.get("url"), "snippet": (x.get("content") or "")[:400]}
        for x in data.get("results", [])[:10]
    ]
    return {"query": query, "results": results}


async def http_request(args: dict) -> dict:
    if not settings.allow_network_tool:
        raise PermissionError("Network tooling is disabled")
    url = str(args["url"])
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are permitted")
    allowlist = settings.http_allowlist_hosts
    if allowlist and (parsed.hostname or "").lower() not in allowlist:
        raise PermissionError(f"Host not in allowlist: {parsed.hostname}")
    method = str(args.get("method", "GET")).upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise ValueError("Unsupported HTTP method")
    body = args.get("body")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.request(
            method,
            url,
            json=body if isinstance(body, (dict, list)) else None,
            content=body if isinstance(body, str) else None,
            headers=args.get("headers") or {},
        )
    return {
        "status_code": r.status_code,
        "headers": dict(r.headers),
        "body": r.text[:20000],
    }


async def fetch_page(args: dict) -> dict:
    if not settings.allow_network_tool:
        raise PermissionError("Network tooling is disabled")
    from bs4 import BeautifulSoup

    url = str(args["url"])
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "ORION/1.0"})
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return {"url": url, "title": (soup.title.string if soup.title else None), "text": text[:20000]}


SHELL_DENY = {"rm", "shutdown", "reboot", "mkfs", "dd", "chmod", "chown", "sudo", "kill", "curl", "wget"}


async def shell_exec(args: dict) -> dict:
    if not settings.allow_shell_tool:
        raise PermissionError("Shell execution is disabled")
    command = str(args["command"]).strip()
    parts = shlex.split(command)
    if not parts:
        raise ValueError("Empty command")
    if parts[0] in SHELL_DENY:
        raise PermissionError(f"Command '{parts[0]}' is denied by policy")
    proc = await asyncio.create_subprocess_exec(
        *parts,
        cwd=str(_knowledge_root()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=settings.shell_timeout_seconds)
    except TimeoutError:
        proc.kill()
        raise TimeoutError("Command timed out") from None
    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", "replace")[:10000],
        "stderr": stderr.decode("utf-8", "replace")[:5000],
    }


async def browse_page(args: dict) -> dict:
    if not settings.allow_browser_tool:
        raise PermissionError("Browser automation is disabled")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Playwright is not installed") from exc

    url = str(args["url"])
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        text = await page.inner_text("body")
        await browser.close()
    return {"url": url, "title": title, "text": text[:20000]}


async def knowledge_search(args: dict) -> dict:
    from app.db.database import SessionLocal
    from app.services.ingestion import search_chunks

    db = SessionLocal()
    try:
        results = await search_chunks(db, str(args["query"]), int(args.get("limit", 5)))
    finally:
        db.close()
    return {"query": args["query"], "results": results}


async def memory_search(args: dict) -> dict:
    from app.db.database import SessionLocal
    from app.services.memory import retrieve_memories

    db = SessionLocal()
    try:
        results = await retrieve_memories(db, str(args["query"]), int(args.get("limit", 5)))
    finally:
        db.close()
    return {"query": args["query"], "results": results}


async def memory_write(args: dict) -> dict:
    from app.db.database import SessionLocal
    from app.services.memory import write_memory

    db = SessionLocal()
    try:
        memory_id = await write_memory(
            db,
            str(args["content"]),
            kind=str(args.get("kind", "fact")),
            key=args.get("key"),
            source="agent",
            confidence=float(args.get("confidence", 0.7)),
        )
    finally:
        db.close()
    return {"id": memory_id, "stored": True}


def register_builtin_tools() -> None:
    defs = [
        ToolDefinition(
            name="calculate",
            description="Safely evaluate a basic arithmetic expression.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "e.g. (2+3)*4"}},
                "required": ["expression"],
            },
            risk="low",
            category="utility",
            handler=calculate,
        ),
        ToolDefinition(
            name="current_time",
            description="Get the current UTC date and time.",
            parameters={"type": "object", "properties": {}},
            risk="low",
            category="utility",
            handler=current_time,
        ),
        ToolDefinition(
            name="list_files",
            description="List files inside ORION's knowledge directory.",
            parameters={"type": "object", "properties": {"path": {"type": "string", "default": "."}}},
            risk="low",
            category="files",
            handler=list_files,
        ),
        ToolDefinition(
            name="read_file",
            description="Read a text file from ORION's knowledge directory.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            risk="low",
            category="files",
            handler=read_file,
        ),
        ToolDefinition(
            name="write_file",
            description="Write a text file into ORION's knowledge directory.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
            risk="high",
            requires_confirmation=True,
            category="files",
            handler=write_file,
        ),
        ToolDefinition(
            name="knowledge_search",
            description="Semantic search over ingested documents (RAG).",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
                "required": ["query"],
            },
            risk="low",
            category="knowledge",
            handler=knowledge_search,
        ),
        ToolDefinition(
            name="memory_search",
            description="Search ORION's long-term memory.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
                "required": ["query"],
            },
            risk="low",
            category="memory",
            handler=memory_search,
        ),
        ToolDefinition(
            name="memory_write",
            description="Store a durable fact or preference in long-term memory.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "kind": {"type": "string", "default": "fact"},
                    "key": {"type": "string"},
                    "confidence": {"type": "number", "default": 0.7},
                },
                "required": ["content"],
            },
            risk="medium",
            category="memory",
            handler=memory_write,
        ),
        ToolDefinition(
            name="web_search",
            description="Search the web through a configured SearXNG instance.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            risk="medium",
            category="web",
            handler=web_search,
        ),
        ToolDefinition(
            name="fetch_page",
            description="Fetch a web page and extract readable text.",
            parameters={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            risk="medium",
            category="network",
            handler=fetch_page,
        ),
        ToolDefinition(
            name="http_request",
            description="Perform an HTTP request against an allowlisted host.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"type": "string", "default": "GET"},
                    "headers": {"type": "object"},
                    "body": {},
                },
                "required": ["url"],
            },
            risk="high",
            requires_confirmation=True,
            category="network",
            handler=http_request,
        ),
        ToolDefinition(
            name="shell_exec",
            description="Run a sandboxed shell command inside the knowledge directory.",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            risk="destructive",
            requires_confirmation=True,
            category="shell",
            handler=shell_exec,
        ),
        ToolDefinition(
            name="browse_page",
            description="Open a page in a headless browser and extract its text.",
            parameters={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            risk="high",
            requires_confirmation=True,
            category="browser",
            handler=browse_page,
        ),
    ]
    for tool in defs:
        registry.register(tool)


register_builtin_tools()

__all__ = ["register_builtin_tools", "safe_eval", "registry", "json"]
