import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.models.project import (
    CodeAnalysisResult,
    DbAnalysisResult,
    Project,
    ProjectStatus,
    SecurityAnalysisResult,
)
from app.routes.deps import CurrentPrincipal, DbSession, Principal
from app.schemas.schemas import (
    CodeResultOut,
    DbResultOut,
    ErDiagramOut,
    ProjectStatusOut,
    SecurityResultOut,
)
from app.services import access
from app.services.analysis_runner import run_analysis

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def _restart(db, principal: Principal, project_id: uuid.UUID, background) -> ProjectStatusOut:
    """Re-run every analysis of a project (staff only; it runs automatically on submit)."""
    project = access.get_project_for(db, principal, project_id)
    access.require_project_staff(db, principal, project)
    if project.status is ProjectStatus.analyzing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Analysis already in progress")
    project.status = ProjectStatus.analyzing
    project.analysis_error = None
    db.commit()
    background.add_task(run_analysis, project_id)
    return ProjectStatusOut(
        id=project.id, status=project.status, analysis_error=None, updated_at=project.updated_at
    )


@router.post(
    "/code/{project_id}", response_model=ProjectStatusOut, status_code=status.HTTP_202_ACCEPTED
)
def start_code_analysis(
    project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, background: BackgroundTasks
):
    return _restart(db, principal, project_id, background)


@router.post(
    "/database/{project_id}",
    response_model=ProjectStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_database_analysis(
    project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, background: BackgroundTasks
):
    project: Project = access.get_project_for(db, principal, project_id)
    if project.db_schema_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project has no database file")
    return _restart(db, principal, project_id, background)


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


@router.get("/database/{project_id}/results", response_model=DbResultOut)
def database_results(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    return _result(db, principal, project_id, DbAnalysisResult)


@router.get("/database/{project_id}/er-diagram", response_model=ErDiagramOut)
def er_diagram(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    result = _result(db, principal, project_id, DbAnalysisResult)
    return ErDiagramOut(project_id=project_id, diagram=result.er_diagram)
