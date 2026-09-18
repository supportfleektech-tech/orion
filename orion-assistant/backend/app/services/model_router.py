from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[Any] = field(default_factory=list)
    message: Any = None
    latency_ms: int = 0
    degraded: bool = False
    error: str | None = None


class _OfflineMessage:
    role = "assistant"
    tool_calls: list[Any] = []

    def __init__(self, content: str) -> None:
        self.content = content

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {"role": "assistant", "content": self.content}


OFFLINE_NOTE = (
    "No language model backend is currently reachable.\n\n"
    "ORION is running in degraded mode: memory, knowledge retrieval, tools and the API "
    "remain fully functional, but generative answers require a model provider.\n\n"
    "To enable responses, either:\n"
    "1. Start Ollama locally and pull a model (`ollama pull qwen3:4b`), or\n"
    "2. Set `OPENROUTER_API_KEY` in your environment to use free cloud routing."
)


class ModelRouter:
    """Local-first model gateway with cloud escalation, failover and degraded mode."""

    def __init__(self) -> None:
        self._local: AsyncOpenAI | None = None
        self._cloud: AsyncOpenAI | None = None
        self.stats: dict[str, Any] = {
            "calls": 0,
            "local_calls": 0,
            "cloud_calls": 0,
            "failures": 0,
            "degraded_calls": 0,
            "last_error": None,
            "total_latency_ms": 0,
        }

    @property
    def local(self) -> AsyncOpenAI:
        if self._local is None:
            self._local = AsyncOpenAI(
                base_url=settings.ollama_base_url,
                api_key=settings.ollama_api_key,
                timeout=settings.request_timeout_seconds,
                max_retries=0,
            )
        return self._local

    @property
    def cloud(self) -> AsyncOpenAI | None:
        if not settings.openrouter_api_key:
            return None
        if self._cloud is None:
            self._cloud = AsyncOpenAI(
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
                timeout=settings.request_timeout_seconds,
                max_retries=1,
                default_headers={
                    "HTTP-Referer": settings.openrouter_http_referer,
                    "X-Title": settings.openrouter_x_title,
                },
            )
        return self._cloud

    def plan(self, mode: str, complexity: str) -> list[tuple[str, str]]:
        """Ordered list of (provider, model) attempts."""
        local = ("local", settings.ollama_model)
        cloud_models = [("cloud", m) for m in settings.openrouter_models] if self.cloud else []

        if settings.local_only or mode == "local":
            return [local]
        if mode == "cloud":
            return cloud_models + [local] if cloud_models else [local]
        if complexity in {"heavy", "expert", "research"} and settings.cloud_escalation_enabled:
            return cloud_models + [local] if cloud_models else [local]
        return [local, *cloud_models]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        mode: str = "auto",
        complexity: str = "normal",
        temperature: float = 0.2,
    ) -> ModelResponse:
        attempts = self.plan(mode, complexity)
        started = time.perf_counter()
        last_error: Exception | None = None
        self.stats["calls"] += 1

        for provider, model in attempts:
            client = self.local if provider == "local" else self.cloud
            if client is None:
                continue
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools or None,
                    temperature=temperature,
                )
                message = response.choices[0].message
                latency = int((time.perf_counter() - started) * 1000)
                self.stats[f"{provider}_calls"] += 1
                self.stats["total_latency_ms"] += latency
                return ModelResponse(
                    text=message.content or "",
                    provider=provider,
                    model=model,
                    usage=response.usage.model_dump() if response.usage else {},
                    tool_calls=list(message.tool_calls or []),
                    message=message,
                    latency_ms=latency,
                )
            except Exception as exc:
                last_error = exc
                self.stats["failures"] += 1
                self.stats["last_error"] = f"{provider}:{model}: {exc}"[:300]
                log.warning("Model attempt failed provider=%s model=%s err=%s", provider, model, exc)

        if not settings.offline_fallback_enabled:
            raise RuntimeError(f"All model providers failed: {last_error}")

        self.stats["degraded_calls"] += 1
        return ModelResponse(
            text=OFFLINE_NOTE,
            provider="offline",
            model="degraded",
            message=_OfflineMessage(OFFLINE_NOTE),
            latency_ms=int((time.perf_counter() - started) * 1000),
            degraded=True,
            error=str(last_error) if last_error else "no provider configured",
        )

    async def health(self) -> dict[str, Any]:
        out = {"local": {"configured": True, "reachable": False, "model": settings.ollama_model},
               "cloud": {"configured": bool(self.cloud), "reachable": False, "model": settings.openrouter_model}}
        try:
            await self.local.models.list()
            out["local"]["reachable"] = True
        except Exception as exc:
            out["local"]["error"] = str(exc)[:200]
        if self.cloud:
            try:
                await self.cloud.models.list()
                out["cloud"]["reachable"] = True
            except Exception as exc:
                out["cloud"]["error"] = str(exc)[:200]
        return out


router = ModelRouter()
