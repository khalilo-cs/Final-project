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


@lru_cache
def get_settings() -> Settings:
    return Settings()
