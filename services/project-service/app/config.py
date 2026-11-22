from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./projects.db"
    storage_dir: str = "./storage"
    # Durable analysis queue: parallel jobs per process, and how often the queue is polled
    # (0 disables the poller; requests still start their own job right away).
    analysis_workers: int = 4
    # Projects submitted as a Git link (https only, these hosts only: no internal addresses).
    git_allowed_hosts: list[str] = ["github.com", "gitlab.com", "bitbucket.org", "codeberg.org"]
    git_clone_timeout_seconds: int = 180
    job_poll_seconds: float = 15
    # Single-replica deployments: at startup every "running" job belonged to the dead process.
    recover_all_running_jobs: bool = True
    # base64 of 32 random bytes; uploaded files are AES-256-GCM encrypted at rest when set.
    storage_encryption_key: str = ""

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
    smtp_from: str = "Mihakk <no-reply@localhost>"
    public_url: str = "http://localhost:8080"


@lru_cache
def get_settings() -> Settings:
    return Settings()
