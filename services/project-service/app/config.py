from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./projects.db"
    storage_dir: str = "./storage"

    # Same secret as auth-service: access tokens are verified locally.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    auth_service_url: str = "http://localhost:8001"
    code_analyzer_url: str = "http://localhost:8003"
    db_analyzer_url: str = "http://localhost:8004"
    report_analyzer_url: str = "http://localhost:8005"
    viva_engine_url: str = "http://localhost:8006"
    fraud_detector_url: str = "http://localhost:8007"
    sandbox_runner_url: str = "http://localhost:8008"
    report_generator_url: str = "http://localhost:8009"
    analyzer_timeout_seconds: float = 300

    max_code_mb: int = 50
    max_report_mb: int = 20
    max_sql_mb: int = 20

    # Optional e-mail copies of notifications (in-app notifications always work).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_from: str = "AI Project Examiner <no-reply@localhost>"
    public_url: str = "http://localhost:8080"


@lru_cache
def get_settings() -> Settings:
    return Settings()
