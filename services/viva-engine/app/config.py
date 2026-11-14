from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./viva.db"
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    # -- AI providers ------------------------------------------------------------------
    # The built-in engine ("template") is always on, so the viva works with no model at
    # all. Each model below is used when configured and reachable.
    ollama_url: str | None = None  # e.g. http://ollama:11434 (local, free, private)
    ollama_model: str = "qwen2.5:7b"
    claude_enabled: bool = False  # credentials come from ANTHROPIC_API_KEY
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    openai_compatible_url: str | None = None  # vLLM, LM Studio, llama.cpp server, ...
    openai_compatible_model: str | None = None
    openai_compatible_api_key: str | None = None
    provider_timeout_seconds: float = 60

    # -- viva rules --------------------------------------------------------------------
    max_questions: int = 8
    session_minutes: int = 30

    # -- learning ----------------------------------------------------------------------
    min_reviews_for_calibration: int = 3
    # Knowledge sources faculty may add; empty = any public site (robots.txt respected).
    knowledge_allowed_domains: list[str] = []
    knowledge_max_page_kb: int = 2048


@lru_cache
def get_settings() -> Settings:
    return Settings()
