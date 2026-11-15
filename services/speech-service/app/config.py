from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"

    # Which engine turns speech into text:
    #   "local"  - faster-whisper inside this container (private, needs the model files)
    #   "remote" - any server with the OpenAI /v1/audio/transcriptions API
    #              (whisper.cpp server, speaches, LocalAI, vLLM, a hosted Whisper ...)
    #   "off"    - disabled; the browser falls back to its own speech recognition
    speech_backend: str = "local"
    whisper_model: str = "small"  # tiny / base / small / medium / large-v3
    whisper_device: str = "cpu"  # or "cuda"
    whisper_compute_type: str = "int8"  # int8 on CPU, float16 on GPU
    whisper_model_dir: str = "/models"  # downloaded once, kept in a volume
    remote_url: str | None = None  # e.g. http://whisper:8000
    remote_model: str = "whisper-1"
    remote_api_key: str | None = None
    remote_timeout_seconds: float = 120

    max_audio_mb: int = 10
    max_seconds: int = 300  # one answer, not a lecture


@lru_cache
def get_settings() -> Settings:
    return Settings()
