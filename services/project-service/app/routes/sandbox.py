import uuid

from fastapi import APIRouter, HTTPException, status

from app.models.project import ProjectStatus
from app.routes.deps import CurrentPrincipal, DbSession
from app.services import access
from app.services.performance import refresh, start_run

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])


def _out(row) -> dict:
    return {
        "status": row.status,
        "runs_successfully": row.runs_successfully,
        "overall_performance_score": row.overall_performance_score,
        "error": row.error,
        "details": row.details,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/run/{project_id}", status_code=status.HTTP_202_ACCEPTED)
def run_again(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Run the performance test again (the project's student or its staff)."""
    project = access.get_project_for(db, principal, project_id)
    if project.student_id != principal.id:
        access.require_project_staff(db, principal, project)
    if project.status in (ProjectStatus.analyzing, ProjectStatus.graded):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Project is {project.status.value}")
    return _out(start_run(db, project))


@router.get("/{project_id}/results")
def results(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    access.get_project_for(db, principal, project_id)
    row = refresh(db, project_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No performance test yet")
    return _out(row)
