"""The AI advisor: strengths, weaknesses, improvements and fixes applied on approval."""

import base64
import shutil
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.models.project import AiFixLog, ProjectStatus
from app.routes.deps import CurrentPrincipal, DbSession
from app.services import access, grading, internal_http
from app.services.advisor import build_advice
from app.services.analysis_runner import run_analysis

router = APIRouter(prefix="/api/v1/projects", tags=["advisor"])


class ApplyRequest(BaseModel):
    fix_ids: list[str] = Field(min_length=1, max_length=200)


def _code_request(path: str, project, data: dict | None = None) -> dict:
    with (
        internal_http.client(get_settings().code_analyzer_url, timeout=120) as http,
        open(project.code_path, "rb") as archive,
    ):
        response = http.post(path, files={"file": ("code.zip", archive)}, data=data)
    response.raise_for_status()
    return response.json()


def _fix_log(db, project_id) -> list[dict]:
    return [
        {
            "fix_id": row.fix_id,
            "file": row.file,
            "line": row.line,
            "type": row.type,
            "title": row.title,
            "applied_at": row.applied_at.isoformat(),
        }
        for row in db.scalars(
            select(AiFixLog).where(AiFixLog.project_id == project_id).order_by(AiFixLog.applied_at)
        )
    ]


@router.get("/{project_id}/advice")
def get_advice(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, lang: str = "ar"):
    project = access.get_project_for(db, principal, project_id)
    advice = build_advice(grading.load_results(db, project.id))
    try:
        advice["fixes"] = _code_request("/api/v1/fixes/propose", project)
    except httpx.HTTPError:
        advice["fixes"] = None  # analyzer down: advice still useful without fixes
    advice["applied_fixes"] = _fix_log(db, project.id)
    advice["summary"] = None
    try:
        written = internal_http.post_json(
            get_settings().viva_engine_url,
            "/internal/advice/summary",
            {"findings": {k: advice[k] for k in ("strengths", "weaknesses", "improvements")},
             "language": "en" if lang == "en" else "ar"},
        )  # fmt: skip
        if written.get("summary"):
            advice["summary"] = written
    except httpx.HTTPError:
        pass
    return advice


@router.post("/{project_id}/fixes/apply")
def apply_fixes(
    project_id: uuid.UUID,
    data: ApplyRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    background: BackgroundTasks,
):
    """Only the student who owns the project can approve changes to its code."""
    project = access.get_project_for(db, principal, project_id)
    if project.student_id != principal.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the project's student can approve")
    if project.status in (ProjectStatus.graded, ProjectStatus.analyzing):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Project is {project.status.value}")
    try:
        import json

        result = _code_request(
            "/api/v1/fixes/apply", project, {"fix_ids": json.dumps(data.fix_ids)}
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Code analyzer unavailable"
        ) from exc

    if result["applied"]:
        code_path = Path(project.code_path)
        if project.original_code_path is None:
            original = code_path.with_name("code-original.zip")
            shutil.copyfile(code_path, original)
            project.original_code_path = str(original)
        code_path.write_bytes(base64.b64decode(result["archive_base64"]))
        for fix in result["applied"]:
            db.add(
                AiFixLog(
                    project_id=project.id,
                    fix_id=fix["id"],
                    file=fix["file"],
                    line=fix["line"],
                    type=fix["type"],
                    title=fix["title"],
                    approved_by=principal.id,
                )
            )
        project.status = ProjectStatus.analyzing
        db.commit()
        background.add_task(run_analysis, project.id)
    return {"applied": result["applied"], "skipped": result["skipped"],
            "status": project.status.value}  # fmt: skip


@router.get("/{project_id}/code")
def download_code(
    project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, original: bool = False
):
    project = access.get_project_for(db, principal, project_id)
    path = (
        project.original_code_path if original and project.original_code_path else project.code_path
    )
    name = "code-original.zip" if original and project.original_code_path else "code.zip"
    return FileResponse(path, media_type="application/zip", filename=name)
