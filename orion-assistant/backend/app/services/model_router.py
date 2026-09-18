from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from app.core.config import settings


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    usage: dict[str, Any]
    tool_calls: list[Any]
    message: Any


class ModelRouter:
    """Local-first model gateway with optional cloud escalation and failover."""

    def __init__(self) -> None:
        self.local = AsyncOpenAI(base_url=settings.ollama_base_url, api_key=settings.ollama_api_key)
        self.cloud = (
            AsyncOpenAI(
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
                default_headers={
                    "HTTP-Referer": settings.openrouter_http_referer,
                    "X-Title": settings.openrouter_x_title,
                },
            )
            if settings.openrouter_api_key
            else None
        )

    def _pick(self, mode: str, complexity: str) -> tuple[str, str]:
        if settings.local_only or mode == "local":
            return "local", settings.ollama_model
        if mode == "cloud" and self.cloud:
            return "cloud", settings.openrouter_model
        if complexity in {"heavy", "expert", "research"} and settings.cloud_escalation_enabled and self.cloud:
            return "cloud", settings.openrouter_model
        return "local", settings.ollama_model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        mode: str = "auto",
        complexity: str = "normal",
        temperature: float = 0.2,
    ) -> ModelResponse:
        provider, model = self._pick(mode, complexity)
        client = self.local if provider == "local" else self.cloud
        if client is None:
            provider, model, client = "local", settings.ollama_model, self.local

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools or None,
                temperature=temperature,
            )
        except Exception:
            if provider == "cloud":
                response = await self.local.chat.completions.create(
                    model=settings.ollama_model,
                    messages=messages,
                    tools=tools or None,
                    temperature=temperature,
                )
                provider, model = "local", settings.ollama_model
            else:
                raise

        message = response.choices[0].message
        text = message.content or ""
        tool_calls = list(message.tool_calls or [])
        usage = response.usage.model_dump() if response.usage else {}
        return ModelResponse(
            text=text,
            provider=provider,
            model=model,
            usage=usage,
            tool_calls=tool_calls,
            message=message,
        )


router = ModelRouter()
