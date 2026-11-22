"""Resumable uploads for weak connections and power cuts.

The client sends the file in pieces, each with its CRC-32 and the offset it belongs at.
The server appends a piece only when the offset is exactly where the file ends and the
checksum matches, so pieces can be retried blindly: a repeat or a gap is answered with
the real offset and the client continues from there.
"""

import shutil
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.upload import UploadSession
from app.services import crypto_store, storage

MAX_CHUNK_BYTES = 2 * 1024 * 1024
RECOMMENDED_CHUNK_BYTES = 256 * 1024  # small enough for a 2G/3G link
EXPIRE_HOURS = 48
MAX_ACTIVE_PER_USER = 6
_MB = 1024 * 1024


def _limits() -> dict[str, tuple[int, set[str]]]:
    settings = get_settings()
    return {
        "code": (settings.max_code_mb, {".zip"}),
        "report": (settings.max_report_mb, set(storage.REPORT_EXTENSIONS)),
        "database": (settings.max_sql_mb, {".sql", ".json"}),
    }


def part_path(upload_id: uuid.UUID) -> Path:
    return Path(get_settings().storage_dir) / "uploads" / f"{upload_id}.part"


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def purge_expired(db: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(hours=EXPIRE_HOURS)
    for session in db.scalars(select(UploadSession)).all():
        if _aware(session.updated_at) < cutoff:
            part_path(session.id).unlink(missing_ok=True)
            db.delete(session)
    db.commit()


def create(db: Session, user_id: uuid.UUID, kind: str, filename: str, size: int) -> UploadSession:
    max_mb, extensions = _limits()[kind]
    if Path(filename).suffix.lower() not in extensions:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"File must be one of: {', '.join(sorted(extensions))}"
        )
    if size > max_mb * _MB:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {max_mb} MB")
    purge_expired(db)
    active = db.scalars(select(UploadSession).where(UploadSession.user_id == user_id)).all()
    if len(active) >= MAX_ACTIVE_PER_USER:
        oldest = min(active, key=lambda s: _aware(s.updated_at))
        part_path(oldest.id).unlink(missing_ok=True)
        db.delete(oldest)
    session = UploadSession(user_id=user_id, kind=kind, filename=filename[:300], size=size)
    db.add(session)
    db.commit()
    path = part_path(session.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return session


def get_own(db: Session, user_id: uuid.UUID, upload_id: uuid.UUID) -> UploadSession:
    session = db.get(UploadSession, upload_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return session


def append(db: Session, session: UploadSession, offset: int, data: bytes, crc32: int) -> None:
    path = part_path(session.id)
    on_disk = path.stat().st_size if path.exists() else 0
    if on_disk != session.received:  # a power cut between writing and committing
        with open(path, "ab") as sink:
            sink.truncate(min(on_disk, session.received))
        session.received = min(on_disk, session.received)
        db.commit()
    if offset != session.received:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Offset does not match",
            headers={"Upload-Offset": str(session.received)},
        )
    if not data or len(data) > MAX_CHUNK_BYTES or offset + len(data) > session.size:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid piece size")
    if zlib.crc32(data) != crc32:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Piece was damaged in transit; send it again"
        )
    with open(path, "ab") as sink:
        sink.write(data)
        sink.flush()
    session.received += len(data)
    session.chunks += 1
    session.updated_at = datetime.now(UTC)
    db.commit()


def claim(db: Session, user_id: uuid.UUID, upload_id: uuid.UUID, kind: str, target: Path) -> str:
    """Copy a completed upload into the project folder; returns the original file name.

    The piece file is kept until `discard` (after the submission is committed), so a
    failed submission never costs the student the upload.
    """
    session = get_own(db, user_id, upload_id)
    if session.kind != kind:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Upload is not a {kind} file")
    path = part_path(session.id)
    if session.received != session.size or not path.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload is not complete yet")
    with open(path, "rb") as source:
        head = source.read(8192)
    magic = {
        "code": storage.ZIP_MAGIC,
        "report": (storage.REPORT_EXTENSIONS[Path(session.filename).suffix.lower()],)
        if kind == "report" else None,
        "database": None,
    }[kind]  # fmt: skip
    valid = b"\x00" not in head if magic is None else head.startswith(magic)
    if not valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"'{session.filename}' is not a valid file of this type"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    crypto_store.seal(target)
    filename = session.filename
    db.delete(session)
    return filename


def discard(upload_ids: list[uuid.UUID | None]) -> None:
    for upload_id in upload_ids:
        if upload_id is not None:
            part_path(upload_id).unlink(missing_ok=True)
