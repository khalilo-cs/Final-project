import uuid
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.config import get_settings
from app.models.course import Course
from app.models.project import ProjectStatus, VivaLink
from app.routes.deps import CurrentPrincipal, DbSession
from app.services import access, grading, internal_http
from app.services.viva_context import build_context

router = APIRouter(prefix="/api/v1/viva", tags=["viva"])


class StartRequest(BaseModel):
    language: Literal["ar", "en"] = "ar"


@router.post("/start/{project_id}", status_code=status.HTTP_201_CREATED)
def start_viva(
    project_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    data: StartRequest | None = None,
):
    """The student starts the viva; questions are generated from their analyzed project."""
    project = access.get_project_for(db, principal, project_id)
    if project.student_id != principal.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the project's student")
    if project.status not in (ProjectStatus.analyzed, ProjectStatus.viva_scheduled):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"The viva needs an analyzed project ({project.status.value})"
        )
    results = grading.load_results(db, project.id)
    course = db.get(Course, project.course_id)
    payload = {
        "project_id": str(project.id),
        "student_id": str(project.student_id),
        "staff_ids": [str(course.faculty_id)],
        "language": (data or StartRequest()).language,
        "context": build_context(project, results),
    }
    try:
        state = internal_http.post_json(
            get_settings().viva_engine_url, "/internal/sessions", payload
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Viva engine unavailable") from exc
    db.add(VivaLink(project_id=project.id, session_id=uuid.UUID(state["session_id"])))
    project.status = ProjectStatus.viva_scheduled
    db.commit()
    return state


@router.get("/project/{project_id}")
def project_vivas(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    access.get_project_for(db, principal, project_id)
    grading.latest_viva(db, project_id)  # refresh finished sessions
    links = db.query(VivaLink).filter_by(project_id=project_id).order_by(VivaLink.started_at)
    return [
        {"session_id": str(link.session_id), "status": link.status, "score": link.score,
         "started_at": link.started_at.isoformat()}
        for link in links
    ]  # fmt: skip
