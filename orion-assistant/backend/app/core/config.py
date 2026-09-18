from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ORION"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = Field(alias="DATABASE_URL")

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"
    ollama_model: str = "qwen3:4b"
    ollama_embed_model: str = "nomic-embed-text"
    local_only: bool = False

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_fallback_models: str = ""
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_x_title: str = "ORION Local-First Assistant"

    default_provider: str = "local"
    cloud_escalation_enabled: bool = True
    max_tool_loops: int = 8
    max_context_chunks: int = 8
    memory_similarity_min: float = 0.30

    searxng_base_url: str = "http://localhost:8888"
    enable_web_search: bool = False
    allow_shell_tool: bool = False
    allow_browser_tool: bool = False
    allow_network_tool: bool = False

    jwt_secret: str = "replace-me-in-production"
    admin_token: str = "change-me"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def openrouter_models(self) -> list[str]:
        models = [x.strip() for x in self.openrouter_fallback_models.split(",") if x.strip()]
        return models or [self.openrouter_model]


settings = Settings()
