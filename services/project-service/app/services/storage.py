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


def save_upload(
    upload: UploadFile, target: Path, max_mb: int, magic: tuple[bytes, ...] | None
) -> None:
    """Stream an upload to disk, enforcing a size limit and the file's magic bytes.

    `magic=None` means a text file: the start of the file must not contain NUL bytes.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    head = upload.file.read(8192)
    valid = b"\x00" not in head if magic is None else head.startswith(magic)
    if not valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"'{upload.filename}' is not a valid file of this type"
        )
    size, chunk = 0, head
    with open(target, "wb") as sink:
        while chunk:
            size += len(chunk)
            if size > max_mb * _MB:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, f"'{upload.filename}' exceeds {max_mb} MB"
                )
            sink.write(chunk)
            chunk = upload.file.read(_MB)


def require_extension(filename: str | None, allowed: set[str], label: str) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{label} must be one of: {', '.join(sorted(allowed))}"
        )
    return extension


def report_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in REPORT_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Report must be a PDF or DOCX file")
    return extension


def delete_project_files(project_id: uuid.UUID) -> None:
    shutil.rmtree(project_dir(project_id), ignore_errors=True)
