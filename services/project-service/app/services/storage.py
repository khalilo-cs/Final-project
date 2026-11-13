"""Local file storage for uploads (to be replaced by MinIO in a later phase)."""

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

_MB = 1024 * 1024
REPORT_EXTENSIONS = {".pdf": b"%PDF", ".docx": b"PK\x03\x04"}
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")


def project_dir(project_id: uuid.UUID) -> Path:
    return Path(get_settings().storage_dir).resolve() / str(project_id)


def save_upload(upload: UploadFile, target: Path, max_mb: int, magic: tuple[bytes, ...]) -> None:
    """Stream an upload to disk, enforcing a size limit and the file's magic bytes."""
    target.parent.mkdir(parents=True, exist_ok=True)
    head = upload.file.read(8)
    if not head.startswith(magic):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"'{upload.filename}' is not a valid file of this type"
        )
    size = len(head)
    with open(target, "wb") as sink:
        sink.write(head)
        while chunk := upload.file.read(_MB):
            size += len(chunk)
            if size > max_mb * _MB:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, f"'{upload.filename}' exceeds {max_mb} MB"
                )
            sink.write(chunk)


def report_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in REPORT_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Report must be a PDF or DOCX file")
    return extension


def delete_project_files(project_id: uuid.UUID) -> None:
    shutil.rmtree(project_dir(project_id), ignore_errors=True)
