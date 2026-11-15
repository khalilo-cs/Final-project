from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Fingerprints of every project analyzed so far (the comparison corpus).
    database_url: str = "sqlite:///./fraud.db"

    # Same secret as auth-service. Service tokens only: this service writes the index.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    max_upload_mb: int = 50
    max_extracted_mb: int = 200
    max_files: int = 20000  # .git folders hold many small files
    max_commits: int = 1000

    # -- Semantic similarity (functions rewritten to hide copying) ---------------------
    # Built-in structural comparison: always on, no model needed.
    semantic_min_shape: int = 30  # smaller functions are too generic to compare
    structural_threshold: float = 0.80
    # Optional code-embedding model on any OpenAI-compatible /v1/embeddings server:
    # Ollama (nomic-embed-text, jina/jina-embeddings-v2-base-code), text-embeddings-
    # inference (microsoft/unixcoder-base, CodeBERT), vLLM, ...
    embedding_url: str | None = None
    embedding_model: str = "nomic-embed-text"
    embedding_api_key: str | None = None
    embedding_threshold: float = 0.92  # calibrate per model on known copies
    embedding_timeout_seconds: float = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
