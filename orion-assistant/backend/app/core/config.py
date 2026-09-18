from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "ORION"
    app_version: str = "1.0.0"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Storage. SQLite keeps the product runnable with zero infrastructure;
    # point DATABASE_URL at Postgres+pgvector for production scale.
    database_url: str = Field(default="sqlite:///./orion.db", alias="DATABASE_URL")

    # Local inference (Ollama, OpenAI-compatible)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"
    ollama_model: str = "qwen3:4b"
    ollama_embed_model: str = "nomic-embed-text"
    local_only: bool = False

    # Multimodal input. vision_models lists substrings of model names known to
    # accept images; anything else gets an honest "I cannot see this" note.
    vision_models: str = "qwen3.5,qwen3-vl,qwen2.5vl,gemma3,llava,minicpm-v,llama3.2-vision,moondream"
    whisper_model: str = "base"

    # Self-improvement: distil successful runs into reusable skills. Costs one
    # extra local model call per learnable run; set false to turn it off.
    skill_learning_enabled: bool = True
    max_upload_mb: int = 25

    # Cloud burst (OpenRouter, OpenAI-compatible)
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_fallback_models: str = ""
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_x_title: str = "ORION Local-First Assistant"

    default_provider: str = "local"
    cloud_escalation_enabled: bool = True
    offline_fallback_enabled: bool = True
    request_timeout_seconds: float = 120.0

    max_tool_loops: int = 6
    max_context_chunks: int = 8
    max_history_messages: int = 20
    memory_similarity_min: float = 0.25
    embedding_dim: int = 768

    # Tools
    knowledge_dir: str = "knowledge"
    searxng_base_url: str = "http://localhost:8888"
    enable_web_search: bool = False
    allow_shell_tool: bool = False
    allow_browser_tool: bool = False
    allow_network_tool: bool = False
    shell_timeout_seconds: int = 20
    http_allowlist: str = ""

    # Security
    auth_enabled: bool = False
    admin_token: str = "change-me"
    jwt_secret: str = "replace-me-in-production"
    cors_origins: str = "*"
    rate_limit_per_minute: int = 120

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()] or ["*"]

    @property
    def openrouter_models(self) -> list[str]:
        models = [x.strip() for x in self.openrouter_fallback_models.split(",") if x.strip()]
        return models or [self.openrouter_model]

    @property
    def http_allowlist_hosts(self) -> list[str]:
        return [x.strip().lower() for x in self.http_allowlist.split(",") if x.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
