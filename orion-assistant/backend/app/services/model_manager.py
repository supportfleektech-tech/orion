"""Local model provisioning: hardware detection, tier selection, install and pull.

ORION's default brain is a real local model served by Ollama. This module picks
the right one for the machine it is running on, installs it, and reports honest
progress. Model IDs are configuration, never product guarantees -- the free
local-model landscape moves fast.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass
class ModelTier:
    """A recommended local model for a class of hardware."""

    name: str
    model: str
    min_ram_gb: float
    download_gb: float
    multimodal: bool
    tools: bool
    context: str
    note: str


# Ordered strongest -> smallest. Selection walks this list and takes the first
# tier the machine can actually hold, leaving headroom for the OS and ORION.
MODEL_TIERS: list[ModelTier] = [
    ModelTier(
        name="workstation",
        model="qwen3.5:9b",
        min_ram_gb=14.0,
        download_gb=6.6,
        multimodal=True,
        tools=True,
        context="256K",
        note="Best local quality: native vision, strong agentic tool use.",
    ),
    ModelTier(
        name="vision-focus",
        model="qwen3-vl:8b",
        min_ram_gb=12.0,
        download_gb=5.8,
        multimodal=True,
        tools=True,
        context="128K",
        note="Strongest document/OCR vision at this size.",
    ),
    ModelTier(
        name="recommended",
        model="qwen3.5:4b",
        min_ram_gb=7.0,
        download_gb=3.4,
        multimodal=True,
        tools=True,
        context="256K",
        note="The 8GB sweet spot: multimodal, thinking mode, tool calling.",
    ),
    ModelTier(
        name="compact",
        model="gemma3:4b",
        min_ram_gb=5.0,
        download_gb=3.3,
        multimodal=True,
        tools=False,
        context="128K",
        note=(
            "Vision-capable on modest hardware, but it has no native tool calling, "
            "so the agent loop degrades to plain chat. Only recommended when you "
            "mainly need image understanding."
        ),
    ),
    ModelTier(
        name="minimal",
        model="qwen3:1.7b",
        min_ram_gb=3.0,
        download_gb=1.4,
        multimodal=False,
        tools=True,
        context="32K",
        note="Text-only fallback for very constrained machines.",
    ),
]

EMBED_MODEL = "nomic-embed-text"
EMBED_DOWNLOAD_GB = 0.27


def total_ram_gb() -> float:
    """Total system RAM in GB, best effort across platforms."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3)
    except (ValueError, OSError, AttributeError):
        pass
    try:  # macOS / BSD
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return int(out.stdout.strip()) / (1024**3)
    except Exception:
        pass
    return 8.0  # conservative assumption


def available_ram_gb() -> float:
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024**2)
    except OSError:
        pass
    return total_ram_gb() * 0.6


def free_disk_gb(path: str = "/") -> float:
    try:
        return shutil.disk_usage(path).free / (1024**3)
    except OSError:
        return 0.0


def has_gpu() -> bool:
    if shutil.which("nvidia-smi"):
        try:
            return subprocess.run(["nvidia-smi"], capture_output=True, timeout=8).returncode == 0
        except Exception:
            return False
    return platform.system() == "Darwin" and platform.machine() == "arm64"  # unified memory


def recommend_tier(ram_gb: float | None = None, require_tools: bool = True) -> ModelTier:
    """Pick the best tier this machine can run.

    ORION is an agent, so by default we only auto-recommend models with native
    tool calling -- a vision model that cannot call tools would silently break
    the agent loop. Tiers without tools stay in the catalog for manual choice.
    """
    ram = ram_gb if ram_gb is not None else total_ram_gb()
    for tier in MODEL_TIERS:
        if ram >= tier.min_ram_gb and (tier.tools or not require_tools):
            return tier
    return MODEL_TIERS[-1]


def hardware_report() -> dict[str, Any]:
    ram = total_ram_gb()
    tier = recommend_tier(ram)
    disk = free_disk_gb()
    needed = tier.download_gb + EMBED_DOWNLOAD_GB
    return {
        "platform": f"{platform.system()} {platform.machine()}",
        "cpu_count": os.cpu_count(),
        "total_ram_gb": round(ram, 1),
        "available_ram_gb": round(available_ram_gb(), 1),
        "free_disk_gb": round(disk, 1),
        "gpu_detected": has_gpu(),
        "recommended": {
            "tier": tier.name,
            "model": tier.model,
            "download_gb": tier.download_gb,
            "multimodal": tier.multimodal,
            "tools": tier.tools,
            "context": tier.context,
            "note": tier.note,
        },
        "disk_sufficient": disk >= needed,
        "disk_needed_gb": round(needed, 2),
        "tiers": [
            {
                "tier": t.name,
                "model": t.model,
                "min_ram_gb": t.min_ram_gb,
                "download_gb": t.download_gb,
                "multimodal": t.multimodal,
                "tools": t.tools,
                "fits": ram >= t.min_ram_gb,
            }
            for t in MODEL_TIERS
        ],
    }


# ---------------------------------------------------------------- Ollama API
def ollama_host() -> str:
    return settings.ollama_base_url.removesuffix("/v1").rstrip("/")


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


async def ollama_running(timeout: float = 4.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return (await client.get(f"{ollama_host()}/api/tags")).status_code == 200
    except Exception:
        return False


async def installed_models() -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{ollama_host()}/api/tags")
            response.raise_for_status()
            return [
                {
                    "name": m.get("name"),
                    "size_gb": round(m.get("size", 0) / (1024**3), 2),
                    "family": (m.get("details") or {}).get("family"),
                    "parameter_size": (m.get("details") or {}).get("parameter_size"),
                }
                for m in response.json().get("models", [])
            ]
    except Exception:
        return []


async def model_present(model: str) -> bool:
    names = {m["name"] for m in await installed_models()}
    return model in names or f"{model}:latest" in names or any(n.startswith(f"{model}:") for n in names)


class PullTracker:
    """Tracks an in-flight `ollama pull` so the UI can show real progress."""

    def __init__(self) -> None:
        self.active: dict[str, dict[str, Any]] = {}

    def snapshot(self) -> dict[str, Any]:
        return {name: dict(state) for name, state in self.active.items()}

    async def pull(self, model: str) -> dict[str, Any]:
        """Stream a model pull, recording progress. Returns the final state."""
        if model in self.active and self.active[model].get("status") == "pulling":
            return self.active[model]

        state = {"model": model, "status": "pulling", "percent": 0.0, "detail": "starting", "error": None}
        self.active[model] = state

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", f"{ollama_host()}/api/pull", json={"model": model, "stream": True}
                ) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"Ollama returned {response.status_code}")
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get("error"):
                            raise RuntimeError(event["error"])
                        total, done = event.get("total"), event.get("completed")
                        if total:
                            state["percent"] = round((done or 0) / total * 100, 1)
                        state["detail"] = event.get("status", "")[:120]
            state.update(status="ready", percent=100.0, detail="complete")
            log.info("Model %s pulled successfully", model)
        except Exception as exc:
            state.update(status="failed", error=str(exc)[:300], detail="failed")
            log.error("Model pull failed for %s: %s", model, exc)
        return state


tracker = PullTracker()


async def provision(model: str | None = None, include_embeddings: bool = True) -> dict[str, Any]:
    """Ensure the chosen model (and the embedder) are available locally."""
    target = model or recommend_tier().model

    if not ollama_installed() and not await ollama_running():
        return {
            "ok": False,
            "stage": "ollama_missing",
            "message": (
                "Ollama is not installed or not reachable. Install it with "
                "`curl -fsSL https://ollama.com/install.sh | sh`, or run "
                "`./scripts/setup-local-model.sh` which does this for you."
            ),
        }

    results = {}
    for name in ([target, EMBED_MODEL] if include_embeddings else [target]):
        if await model_present(name):
            results[name] = {"status": "already_present"}
        else:
            results[name] = await tracker.pull(name)

    ok = all(r.get("status") in {"ready", "already_present"} for r in results.values())
    if ok:
        settings.ollama_model = target
        settings.ollama_embed_model = EMBED_MODEL
    return {"ok": ok, "model": target, "results": results}


async def status() -> dict[str, Any]:
    running = await ollama_running()
    models = await installed_models() if running else []
    active = settings.ollama_model
    return {
        "ollama_installed": ollama_installed(),
        "ollama_running": running,
        "host": ollama_host(),
        "active_model": active,
        "active_model_present": any(m["name"].split(":")[0] == active.split(":")[0] for m in models),
        "embed_model": settings.ollama_embed_model,
        "embed_model_present": any(m["name"].startswith(EMBED_MODEL) for m in models),
        "installed_models": models,
        "vision_capable": any(
            tag.strip() and tag.strip() in active.lower() for tag in settings.vision_models.split(",")
        ),
        "pulls": tracker.snapshot(),
        "hardware": hardware_report(),
    }
