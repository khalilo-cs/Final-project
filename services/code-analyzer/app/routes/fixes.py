import base64
import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.config import get_settings
from app.fixes import service
from app.routes.deps import CurrentClaims
from app.services.archive import ArchiveError, extract_zip

router = APIRouter(prefix="/api/v1/fixes", tags=["fixes"])
_MB = 1024 * 1024


def _unpack(file: UploadFile, workdir: str) -> tuple[Path, Path]:
    settings = get_settings()
    archive = Path(workdir) / "upload.zip"
    data = file.file.read(settings.max_upload_mb * _MB + 1)
    if len(data) > settings.max_upload_mb * _MB:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Upload is too large")
    archive.write_bytes(data)
    root = Path(workdir) / "project"
    root.mkdir()
    try:
        extract_zip(archive, root, settings.max_extracted_mb * _MB, settings.max_files)
    except ArchiveError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return root, archive


@router.post("/propose")
def propose(file: UploadFile, _: CurrentClaims):
    """Fixes for the findings in a project: patches (applicable) and suggestions."""
    with tempfile.TemporaryDirectory(prefix="aipe-fix-") as workdir:
        root, _archive = _unpack(file, workdir)
        return service.propose(root)


@router.post("/apply")
def apply(
    file: UploadFile,
    _: CurrentClaims,
    fix_ids: Annotated[str, Form(description="JSON list of fix ids the student approved")],
):
    try:
        ids = json.loads(fix_ids)
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "fix_ids must be a JSON list of strings"
        ) from exc
    with tempfile.TemporaryDirectory(prefix="aipe-fix-") as workdir:
        root, archive = _unpack(file, workdir)
        content, applied, skipped = service.apply(root, archive, ids)
    return {
        "applied": applied,
        "skipped": skipped,
        "archive_base64": base64.b64encode(content).decode() if applied else None,
    }
