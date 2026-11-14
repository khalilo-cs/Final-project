from collections import Counter

from fastapi import APIRouter
from sqlalchemy import select

from app.models.course import Course
from app.models.project import Project
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.services import grading
from app.services.alerts import project_alerts, sort_alerts

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _staff_projects(db, principal) -> list[Project]:
    if principal.is_admin:
        return list(db.scalars(select(Project)))
    if principal.is_faculty:
        return list(
            db.scalars(select(Project).join(Course).where(Course.faculty_id == principal.id))
        )
    raise forbidden()


@router.get("/faculty/summary")
def summary(db: DbSession, principal: CurrentPrincipal):
    projects = _staff_projects(db, principal)
    statuses = Counter(project.status.value for project in projects)
    criterion_totals: dict[str, list[float]] = {c: [] for c in grading.CRITERIA}
    suggested, alert_count = [], 0
    for project in projects:
        results = grading.load_results(db, project.id)
        suggestion = grading.suggest(grading.course_weights(db, project.course_id), results)
        if suggestion.suggested_total is not None:
            suggested.append(suggestion.suggested_total)
        for criterion, score in suggestion.scores.items():
            if score is not None:
                criterion_totals[criterion].append(score)
        alert_count += len(project_alerts(project, results))

    def average(values):
        return round(sum(values) / len(values), 1) if values else None

    return {
        "total_projects": len(projects),
        "by_status": dict(statuses),
        "average_suggested_total": average(suggested),
        "average_by_criterion": {c: average(v) for c, v in criterion_totals.items()},
        "alerts": alert_count,
    }


@router.get("/faculty/alerts")
def alerts(db: DbSession, principal: CurrentPrincipal):
    found = []
    for project in _staff_projects(db, principal):
        found += project_alerts(project, grading.load_results(db, project.id))
    return sort_alerts(found)
