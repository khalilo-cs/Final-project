"""Service configuration, read from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./auth.db"

    # No default on purpose: the service must not start with a guessable secret.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Optional first admin, created at startup when no admin exists yet.
    admin_username: str | None = None
    admin_email: str | None = None
    admin_password: str | None = None

    cors_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
