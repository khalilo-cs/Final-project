import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.analyzers import semantic
from app.analyzers.git_history import analyze_git
from app.analyzers.similarity import compare_and_index, remove_document
from app.analyzers.style import analyze_style
from app.archive import ArchiveError, extract_zip
from app.config import get_settings
from app.routes.deps import DbSession, ServiceClaims

router = APIRouter(prefix="/api/v1", tags=["fraud"])
_MB = 1024 * 1024


@router.post("/fraud/analyze")
def analyze(
    file: UploadFile,
    db: DbSession,
    _: ServiceClaims,
    document_id: Annotated[str, Form(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    exclude_ids: Annotated[
        str, Form(description="JSON list: same student's other projects")
    ] = "[]",
    index: Annotated[bool, Form()] = True,
):
    """Similarity with earlier projects, Git history and style consistency."""
    try:
        exclude = set(json.loads(exclude_ids))
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "exclude_ids must be JSON"
        ) from exc
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="aipe-fraud-") as workdir:
        archive = Path(workdir) / "code.zip"
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
        similarity = compare_and_index(db, document_id, root, exclude, index)
        token_lines: dict[str, dict[str, list]] = {}
        for source in similarity["sources"]:
            for match in source["matched_files"]:
                files = token_lines.setdefault(source["document_id"], {})
                files.setdefault(match["file"], []).append(tuple(match["lines"]))
        return {
            "similarity": similarity,
            "semantic": semantic.compare_and_index(
                db, document_id, root, exclude, token_lines, index
            ),
            "git": analyze_git(root),
            "style": analyze_style(root),
        }


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget(document_id: str, db: DbSession, _: ServiceClaims):
    remove_document(db, document_id)
