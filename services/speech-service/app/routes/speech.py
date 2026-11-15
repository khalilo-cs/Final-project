from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import get_settings
from app.engines import Engine, TranscriptionError, get_engine
from app.routes.deps import UserClaims

router = APIRouter(prefix="/api/v1/speech", tags=["speech"])
# Containers browsers record in (MediaRecorder) plus common uploads.
_AUDIO_MAGIC = (
    b"\x1aE\xdf\xa3",  # WebM / Matroska (Chrome, Firefox)
    b"OggS",  # Ogg / Opus
    b"RIFF",  # WAV
    b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2",  # MP3
    b"fLaC",
)  # fmt: skip


class Status(BaseModel):
    available: bool
    engine: str
    reason: str | None = None
    max_audio_mb: int
    max_seconds: int


class TranscriptOut(BaseModel):
    text: str
    language: str | None
    duration: float | None
    engine: str


EngineDep = Annotated[Engine, Depends(get_engine)]


def _is_audio(head: bytes) -> bool:
    # MP4/M4A (Safari) has "ftyp" at offset 4.
    return head.startswith(_AUDIO_MAGIC) or head[4:8] == b"ftyp"


@router.get("/status", response_model=Status)
def speech_status(_: UserClaims, engine: EngineDep):
    """Lets the viva page choose server transcription or the browser's own."""
    available, reason = engine.available()
    settings = get_settings()
    return Status(
        available=available, engine=engine.name, reason=reason,
        max_audio_mb=settings.max_audio_mb, max_seconds=settings.max_seconds,
    )  # fmt: skip


@router.post("/transcribe", response_model=TranscriptOut)
def transcribe(
    _: UserClaims,
    engine: EngineDep,
    audio: Annotated[UploadFile, File(description="Recorded answer (webm/ogg/wav/mp3/m4a)")],
    language: Annotated[Literal["ar", "en", "auto"], Form()] = "ar",
    prompt: Annotated[str | None, Form(max_length=1000)] = None,
):
    """Speech -> text. `prompt` (e.g. the viva question) helps with technical words."""
    available, reason = engine.available()
    if not available:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, reason or "unavailable")
    settings = get_settings()
    limit = settings.max_audio_mb * 1024 * 1024
    data = audio.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Audio is larger than {settings.max_audio_mb} MB"
        )
    if not data or not _is_audio(data[:12]):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a supported audio file")
    try:
        result = engine.transcribe(data, None if language == "auto" else language, prompt)
    except TranscriptionError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcription failed") from exc
    if result.duration and result.duration > settings.max_seconds:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Answers are limited to {settings.max_seconds} s"
        )
    return TranscriptOut(**result.__dict__)
