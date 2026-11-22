"""The remaining endpoints of the plan's API list (section 4.4).

Most of them expose, under the names the plan uses, data other routes already
compute; the logic lives in those routes and services.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import func, select

from app.audit import AuditEntry
from app.models.course import Course
from app.models.project import Project
from app.routes import analysis, dashboard, fraud, grades
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.schemas.schemas import ProjectStatusOut
from app.services import access, jobs, learning, student_report
from app.services.performance import refresh

router = APIRouter(prefix="/api/v1", tags=["plan"])


@router.post(
    "/analysis/security/{project_id}",
    response_model=ProjectStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_security_analysis(
    project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, background: BackgroundTasks
):
    """Security is scanned together with the code: this re-runs the analysis."""
    return analysis._restart(db, principal, project_id, background)


@router.post(
    "/fraud/analyze/{project_id}",
    response_model=ProjectStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_fraud_analysis(
    project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, background: BackgroundTasks
):
    return analysis._restart(db, principal, project_id, background)


@router.get("/fraud/{project_id}/similar-projects")
def similar_projects(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    result = fraud.fraud_results(project_id, db, principal)
    return {
        "similar_projects": result["similar_projects"],
        "rewritten_code": result["rewritten_code"],
    }


def _performance(db, principal, project_id):
    access.get_project_for(db, principal, project_id)
    row = refresh(db, project_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No performance test yet")
    return row


@router.get("/sandbox/{project_id}/status")
def sandbox_status(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    row = _performance(db, principal, project_id)
    return {"status": row.status, "phase": (row.details or {}).get("phase"), "error": row.error}


@router.get("/sandbox/{project_id}/screenshots")
def sandbox_screenshots(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    row = _performance(db, principal, project_id)
    return {"status": row.status, "screenshots": (row.details or {}).get("screenshots", [])}


@router.get("/reports/student/{project_id}")
def student_report_json(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """The data of the PDF report, as JSON (same audience rules as the PDF)."""
    project = access.get_project_for(db, principal, project_id)
    audience = "student" if project.student_id == principal.id else "staff"
    if audience == "staff":
        access.require_project_staff(db, principal, project)
    try:
        return student_report.build_payload(db, project, audience)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "A service is unavailable"
        ) from exc


@router.get("/reports/course/{course_id}")
def course_report(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    return grades.course_grades(course_id, db, principal)


@router.get("/reports/analytics/department")
def department_report(db: DbSession, principal: CurrentPrincipal):
    return dashboard.department_analytics(db, principal)


@router.get("/dashboard/admin/stats")
def admin_stats(db: DbSession, principal: CurrentPrincipal):
    """System health for the admin: volumes, analysis queue, activity."""
    if not principal.is_admin:
        raise forbidden()
    by_status = dict(
        db.execute(select(Project.status, func.count()).group_by(Project.status)).all()
    )
    day_ago = datetime.now(UTC) - timedelta(days=1)
    return {
        "projects": sum(by_status.values()),
        "projects_by_status": {
            str(k.value if hasattr(k, "value") else k): v for k, v in by_status.items()
        },  # fmt: skip
        "courses": db.scalar(select(func.count()).select_from(Course)),
        "students_with_projects": db.scalar(select(func.count(func.distinct(Project.student_id)))),
        "analysis_queue": jobs.counts(),
        "audited_actions_24h": db.scalar(
            select(func.count()).select_from(AuditEntry).where(AuditEntry.at >= day_ago)
        ),
        "failed_requests_24h": db.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.at >= day_ago, AuditEntry.status_code >= 500)
        ),
    }


@router.get("/courses/{course_id}/criteria/learned")
def learned_weights(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Weights fitted to the faculty's own approved grades (FR-12.2); apply with PUT criteria."""
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    return asdict(learning.learn_weights(db, course_id))


@router.get("/fraud/course/{course_id}/rings")
def course_copy_rings(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Groups of 3+ projects linked by similarity: a shared source (FR-12.4). Staff only."""
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    return learning.copy_rings(db, course_id)
