"""Connectors: the external services ORION can reach, and whether they answer.

Every integration here is configured by environment variable and probed live.
There is deliberately no OAuth flow and no credential store: ORION is
local-first, so a connector is a URL you control plus, at most, one API key you
already have. Storing third-party refresh tokens would make this a credential
vault, which is a very different security posture and is explicitly out of
scope for v1.

The value of this module is answering one question honestly -- "is it actually
plugged in?" -- because a misconfigured base URL otherwise only surfaces as a
degraded answer much later.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.services import mcp_client

log = logging.getLogger(__name__)

PROBE_TIMEOUT = 4.0

Status = Literal["connected", "unreachable", "not_configured", "disabled"]


@dataclass
class Connector:
    id: str
    name: str
    category: str
    summary: str
    status: Status
    detail: str
    endpoint: str | None = None
    required: bool = False
    docs: str | None = None
    #: Env vars that configure this connector. Names only -- never values.
    env_keys: list[str] | None = None

    def dict(self) -> dict[str, Any]:
        return asdict(self)


async def _reachable(url: str, *, expect_json: bool = False) -> tuple[bool, str]:
    """Probe a URL. Returns (ok, human explanation)."""
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        return False, f"No response within {PROBE_TIMEOUT:g}s"
    except httpx.HTTPError as exc:
        # The message is usually more useful than the exception class.
        return False, str(exc) or exc.__class__.__name__

    if response.status_code >= 500:
        return False, f"HTTP {response.status_code} from the service"
    if response.status_code in (401, 403):
        return False, f"HTTP {response.status_code} -- credentials rejected"
    if expect_json:
        try:
            response.json()
        except ValueError:
            return False, "Responded, but not with JSON -- check the base URL"
    return True, f"HTTP {response.status_code}"


async def _local_model() -> Connector:
    base = settings.ollama_base_url.rstrip("/")
    ok, detail = await _reachable(f"{base}/models", expect_json=True)
    return Connector(
        id="ollama",
        name="Local model runtime",
        category="Inference",
        summary="Runs the model on this machine. ORION works fully offline with it.",
        status="connected" if ok else "unreachable",
        detail=f"{settings.ollama_model} · {detail}" if ok else detail,
        endpoint=base,
        required=True,
        docs="docs/LOCAL_MODELS.md",
        env_keys=["OLLAMA_BASE_URL", "OLLAMA_MODEL"],
    )


async def _cloud_model() -> Connector:
    if not settings.openrouter_api_key:
        return Connector(
            id="openrouter",
            name="Cloud model routing",
            category="Inference",
            summary="Optional burst capacity when a task is too large for the local model.",
            status="not_configured",
            detail="No API key set. ORION stays local-only, which is a valid setup.",
            endpoint=settings.openrouter_base_url,
            docs="docs/ARCHITECTURE.md",
            env_keys=["OPENROUTER_API_KEY", "OPENROUTER_MODEL"],
        )

    if settings.local_only:
        return Connector(
            id="openrouter",
            name="Cloud model routing",
            category="Inference",
            summary="Optional burst capacity when a task is too large for the local model.",
            status="disabled",
            detail="Configured, but local-only mode is on so nothing will be sent.",
            endpoint=settings.openrouter_base_url,
            env_keys=["OPENROUTER_API_KEY", "OPENROUTER_MODEL"],
        )

    base = settings.openrouter_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
        ok = response.status_code < 400
        detail = f"{settings.openrouter_model} · HTTP {response.status_code}"
        if response.status_code in (401, 403):
            detail = "Key rejected -- check OPENROUTER_API_KEY"
    except httpx.HTTPError as exc:
        ok, detail = False, str(exc) or exc.__class__.__name__

    return Connector(
        id="openrouter",
        name="Cloud model routing",
        category="Inference",
        summary="Optional burst capacity when a task is too large for the local model.",
        status="connected" if ok else "unreachable",
        detail=detail,
        endpoint=base,
        env_keys=["OPENROUTER_API_KEY", "OPENROUTER_MODEL"],
    )


async def _embeddings() -> Connector:
    base = settings.ollama_base_url.rstrip("/")
    ok, detail = await _reachable(f"{base}/models", expect_json=True)
    return Connector(
        id="embeddings",
        name="Embeddings",
        category="Retrieval",
        summary="Vectorises documents for semantic search.",
        status="connected" if ok else "unreachable",
        detail=(
            f"{settings.ollama_embed_model} via the local runtime"
            if ok
            else "Falls back to a deterministic hashed embedder, so retrieval still works"
        ),
        endpoint=base,
        env_keys=["OLLAMA_EMBED_MODEL"],
    )


async def _web_search() -> Connector:
    if not settings.enable_web_search:
        return Connector(
            id="searxng",
            name="Web search",
            category="Tools",
            summary="Private metasearch through a SearXNG instance you run.",
            status="disabled",
            detail="Turned off by policy. Enable it in Settings to let ORION search the web.",
            endpoint=settings.searxng_base_url,
            docs="docs/TOOLS_MCP.md",
            env_keys=["ENABLE_WEB_SEARCH", "SEARXNG_BASE_URL"],
        )

    ok, detail = await _reachable(settings.searxng_base_url.rstrip("/"))
    return Connector(
        id="searxng",
        name="Web search",
        category="Tools",
        summary="Private metasearch through a SearXNG instance you run.",
        status="connected" if ok else "unreachable",
        detail=detail if ok else f"{detail} -- start it with: docker compose --profile web-search up",
        endpoint=settings.searxng_base_url,
        env_keys=["ENABLE_WEB_SEARCH", "SEARXNG_BASE_URL"],
    )


def _mcp(db: Any) -> Connector:
    """MCP servers are the real extension point, so surface them as one row."""
    from app.db.models import McpServer

    servers = db.query(McpServer).all()
    enabled = [s for s in servers if s.enabled]
    healthy = [s for s in enabled if s.status == "ok"]
    tools = sum(len(s.tools or []) for s in healthy)

    if not mcp_client.sdk_available():
        status: Status = "not_configured"
        detail = "The mcp package is not installed (see requirements-optional.txt)"
    elif not servers:
        status = "not_configured"
        detail = "No servers registered yet"
    elif len(healthy) == len(enabled):
        status = "connected"
        detail = f"{len(healthy)} server(s), {tools} tools"
    else:
        status = "unreachable"
        broken = ", ".join(s.name for s in enabled if s.status != "ok")
        detail = f"{len(healthy)}/{len(enabled)} healthy · failing: {broken}"

    return Connector(
        id="mcp",
        name="MCP servers",
        category="Tools",
        summary="Attach external tool servers -- filesystems, trackers, databases, your own.",
        status=status,
        detail=detail,
        docs="docs/MCP.md",
        env_keys=[],
    )


async def status(db: Any) -> dict[str, Any]:
    """Probe every connector concurrently and summarise."""
    probes = await asyncio.gather(
        _local_model(), _cloud_model(), _embeddings(), _web_search(), return_exceptions=True
    )

    connectors: list[Connector] = []
    for probe in probes:
        if isinstance(probe, BaseException):
            # A probe must never take the page down with it.
            log.warning("Connector probe failed", exc_info=probe)
            continue
        connectors.append(probe)

    try:
        connectors.append(_mcp(db))
    except Exception:
        log.warning("MCP connector probe failed", exc_info=True)

    return {
        "connectors": [c.dict() for c in connectors],
        "connected": sum(1 for c in connectors if c.status == "connected"),
        "total": len(connectors),
        "local_only": settings.local_only,
    }
