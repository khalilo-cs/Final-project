from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Same secret as auth-service: access tokens are verified locally.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    max_upload_mb: int = 50
    max_extracted_mb: int = 200
    max_files: int = 5000


@lru_cache
def get_settings() -> Settings:
    return Settings()
