from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    # Limits for the student's code (plan, week 20).
    cpus: float = 1.0
    memory_mb: int = 512
    pids_limit: int = 256
    build_timeout_seconds: int = 300
    startup_timeout_seconds: int = 60
    run_timeout_seconds: int = 300
    # The run container joins only this network: no internet, reachable by the runner.
    sandbox_network: str = "aipe-sandbox"

    load_levels: list[int] = [1, 10, 50]
    requests_per_level: int = 100
    max_upload_mb: int = 50
    max_extracted_mb: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
