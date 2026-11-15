"""Speech-to-text engines behind one interface.

Audio never leaves the university's servers with the local engine; the remote engine
sends it only to the server the administrator configured.
"""

import io
import logging
import threading
from dataclasses import dataclass
from functools import cache
from typing import Protocol

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


class TranscriptionError(Exception):
    pass


@dataclass
class Transcript:
    text: str
    language: str | None
    duration: float | None
    engine: str


class Engine(Protocol):
    name: str

    def available(self) -> tuple[bool, str | None]: ...

    def transcribe(self, audio: bytes, language: str | None, prompt: str | None) -> Transcript: ...


class LocalWhisper:
    """faster-whisper (CTranslate2). The model loads once, on first use."""

    name = "local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def available(self) -> tuple[bool, str | None]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper is not installed in this image"
        return True, None

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                s = self.settings
                log.info("loading Whisper model %s on %s", s.whisper_model, s.whisper_device)
                self._model = WhisperModel(
                    s.whisper_model,
                    device=s.whisper_device,
                    compute_type=s.whisper_compute_type,
                    download_root=s.whisper_model_dir,
                )
            return self._model

    def transcribe(self, audio: bytes, language: str | None, prompt: str | None) -> Transcript:
        try:
            model = self._load()
            segments, info = model.transcribe(
                io.BytesIO(audio),
                language=language,
                initial_prompt=prompt,
                vad_filter=True,  # skip silence
                beam_size=5,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # decoding errors, missing model files, ...
            log.exception("local transcription failed")
            raise TranscriptionError(str(exc) or type(exc).__name__) from exc
        return Transcript(text, info.language, round(info.duration, 2), self.name)


class RemoteWhisper:
    """Any server implementing POST /v1/audio/transcriptions."""

    name = "remote"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def available(self) -> tuple[bool, str | None]:
        if not self.settings.remote_url:
            return False, "REMOTE_URL is not set"
        return True, None

    def transcribe(self, audio: bytes, language: str | None, prompt: str | None) -> Transcript:
        s = self.settings
        headers = {"Authorization": f"Bearer {s.remote_api_key}"} if s.remote_api_key else {}
        data = {"model": s.remote_model, "response_format": "json"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        try:
            with httpx.Client(
                base_url=s.remote_url or "",
                timeout=s.remote_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    "/v1/audio/transcriptions",
                    data=data,
                    files={"file": ("answer.webm", audio, "application/octet-stream")},
                    headers=headers,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranscriptionError(f"speech server error ({type(exc).__name__})") from exc
        return Transcript(
            (body.get("text") or "").strip(), body.get("language") or language,
            body.get("duration"), self.name,
        )  # fmt: skip


class Disabled:
    name = "off"

    def available(self) -> tuple[bool, str | None]:
        return False, "speech recognition on the server is turned off"

    def transcribe(self, audio: bytes, language: str | None, prompt: str | None) -> Transcript:
        raise TranscriptionError("disabled")


@cache
def get_engine() -> Engine:
    settings = get_settings()
    backend = settings.speech_backend.lower()
    if backend == "local":
        return LocalWhisper(settings)
    if backend == "remote":
        return RemoteWhisper(settings)
    return Disabled()
