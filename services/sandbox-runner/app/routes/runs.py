import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status

from app import runner
from app.archive import ArchiveError, extract_zip
from app.config import get_settings
from app.routes.deps import ServiceClaims

router = APIRouter(prefix="/internal/runs", tags=["sandbox"])
_MB = 1024 * 1024

# Created on first use so the service starts even where Docker is not reachable.
backend_factory = None


def get_backend():
    from app.sandbox.backend import DockerBackend

    return (backend_factory or DockerBackend)()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_run(file: UploadFile, _: ServiceClaims):
    settings = get_settings()
    holder = tempfile.TemporaryDirectory(prefix="aipe-run-")
    root = Path(holder.name)
    data = file.file.read(settings.max_upload_mb * _MB + 1)
    if len(data) > settings.max_upload_mb * _MB:
        holder.cleanup()
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Upload is too large")
    (root / "code.zip").write_bytes(data)
    (root / "project").mkdir()
    try:
        extract_zip(root / "code.zip", root / "project", settings.max_extracted_mb * _MB, 20000)
    except ArchiveError as exc:
        holder.cleanup()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    try:
        backend = get_backend()
    except Exception as exc:  # noqa: BLE001 - docker missing or socket not mounted
        holder.cleanup()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Docker is not available") from exc
    run_id = runner.new_run()
    runner.start_in_background(run_id, holder, backend)
    return runner.RUNS[run_id]


@router.get("/{run_id}")
def get_run(run_id: str, _: ServiceClaims):
    run = runner.RUNS.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown run")
    return run
