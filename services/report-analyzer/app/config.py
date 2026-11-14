from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Fingerprint index of every report analyzed so far (plagiarism corpus).
    database_url: str = "sqlite:///./reports.db"

    # Same secret as auth-service. Only project-service (role "service") may call this
    # service, because it writes to the shared plagiarism index.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    max_upload_mb: int = 30
    max_pages: int = 400
    max_docx_uncompressed_mb: int = 150


@lru_cache
def get_settings() -> Settings:
    return Settings()
