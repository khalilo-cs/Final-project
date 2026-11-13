import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.config import get_settings
from app.routes.deps import CurrentClaims
from app.services.archive import ArchiveError, extract_zip
from app.services.project_analyzer import analyze_project

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_MB = 1024 * 1024


@router.post("/code")
def analyze_code(file: UploadFile, _: CurrentClaims):
    """Analyze an uploaded ZIP of source code and return code + security results.

    Synchronous for now. Once project-service and the message queue exist this
    becomes `POST /analysis/code/{project_id}` with results fetched separately.
    """
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="aipe-") as workdir:
        archive = Path(workdir) / "upload.zip"
        size = 0
        with open(archive, "wb") as sink:
            while chunk := file.file.read(_MB):
                size += len(chunk)
                if size > settings.max_upload_mb * _MB:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"Upload exceeds {settings.max_upload_mb} MB",
                    )
                sink.write(chunk)

        project = Path(workdir) / "project"
        project.mkdir()
        try:
            extract_zip(archive, project, settings.max_extracted_mb * _MB, settings.max_files)
        except ArchiveError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        return analyze_project(project)
