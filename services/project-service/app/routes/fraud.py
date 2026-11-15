import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.models.course import Course
from app.models.project import FraudResult, Project
from app.routes.deps import CurrentPrincipal, DbSession
from app.services import access, grading, internal_http

router = APIRouter(prefix="/api/v1/fraud", tags=["fraud"])


@router.get("/{project_id}/results")
def fraud_results(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Staff only: suspicion of copying is not shown to students before a professor decides."""
    project = access.get_project_for(db, principal, project_id)
    access.require_project_staff(db, principal, project)
    fraud = db.scalar(select(FraudResult).where(FraudResult.project_id == project_id))
    if fraud is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No authenticity analysis yet")
    results = grading.load_results(db, project_id)

    semantic_sources = (fraud.semantic or {}).get("sources") or []
    ids = []
    for source in [*fraud.similar_projects, *semantic_sources]:
        try:
            ids.append(uuid.UUID(source["document_id"]))
        except ValueError:
            continue
    others = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(ids)))}
    names = internal_http.lookup_users({p.student_id for p in others.values()})

    def describe(source: dict) -> dict:
        try:
            other = others.get(uuid.UUID(source["document_id"]))
        except ValueError:
            other = None
        course = db.get(Course, other.course_id) if other else None
        student = names.get(str(other.student_id), {}) if other else {}
        return {
            **source,
            "submitted": "later" if source["document_id"] in results.later_projects else "earlier",
            "title": other.title if other else "(مشروع محذوف أو سابق)",
            "student_name": student.get("full_name"),
            "course": f"{course.code} - {course.name}" if course else None,
        }

    return {
        **(results.authenticity or {}),
        "similar_projects": [describe(s) for s in fraud.similar_projects],
        "rewritten_code": [describe(s) for s in semantic_sources],
        "semantic_methods": (fraud.semantic or {}).get("methods"),
        "git": fraud.git_analysis,
        "style": fraud.style,
        "analyzed_at": fraud.analyzed_at.isoformat(),
    }
