import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.models.project import CodeAnalysisResult, ProjectStatus, SecurityAnalysisResult
from app.routes.deps import CurrentPrincipal, DbSession
from app.schemas.schemas import CodeResultOut, ProjectStatusOut, SecurityResultOut
from app.services import access
from app.services.analysis_runner import run_code_analysis

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/code/{project_id}",
    response_model=ProjectStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_code_analysis(
    project_id: uuid.UUID,
    db: DbSession,
    principal: CurrentPrincipal,
    background: BackgroundTasks,
):
    """Re-run code + security analysis (staff only; it runs automatically on submit)."""
    project = access.get_project_for(db, principal, project_id)
    access.require_project_staff(db, principal, project)
    if project.status is ProjectStatus.analyzing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Analysis already in progress")
    project.status = ProjectStatus.analyzing
    project.analysis_error = None
    db.commit()
    background.add_task(run_code_analysis, project_id)
    return ProjectStatusOut(
        id=project.id, status=project.status, analysis_error=None, updated_at=project.updated_at
    )


def _result(db, principal, project_id, model):
    access.get_project_for(db, principal, project_id)
    result = db.scalar(select(model).where(model.project_id == project_id))
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No analysis results yet")
    return result


@router.get("/code/{project_id}/results", response_model=CodeResultOut)
def code_results(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    return _result(db, principal, project_id, CodeAnalysisResult)


@router.get("/security/{project_id}/results", response_model=SecurityResultOut)
def security_results(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    return _result(db, principal, project_id, SecurityAnalysisResult)
