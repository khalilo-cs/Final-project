import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.models.course import Course
from app.models.grading import FinalGrade, GradingCriterion, LearningLog
from app.models.project import Project, ProjectStatus
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.schemas.schemas import (
    CriterionOut,
    GradeOut,
    GradeUpdate,
    StudentGradeOut,
    WeightsUpdate,
)
from app.services import access, grading, internal_http, notify
from app.services.alerts import project_alerts
from app.services.excel import grade_sheet

router = APIRouter(prefix="/api/v1", tags=["grades"])


def _grade_out(db, project: Project) -> GradeOut:
    results = grading.load_results(db, project.id)
    suggestion = grading.suggest(grading.course_weights(db, project.course_id), results)
    final = grading.final_grade(db, project.id)
    return GradeOut(
        project_id=project.id,
        status=project.status,
        suggested_total=suggestion.suggested_total,
        coverage=suggestion.coverage,
        missing_criteria=suggestion.missing,
        breakdown=suggestion.breakdown,
        final_total=final.faculty_adjusted_total if final else None,
        faculty_notes=final.faculty_notes if final else None,
        graded_at=final.graded_at if final else None,
        alerts=project_alerts(project, results),
    )


# -- weights ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/criteria", response_model=list[CriterionOut])
def get_criteria(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    course = access.get_course(db, course_id)
    access.require_course_view(db, principal, course)
    weights = grading.course_weights(db, course_id)
    return [
        CriterionOut(
            criterion=c,
            label_ar=grading.LABELS_AR[c],
            weight=weights[c],
            is_default=weights[c] == grading.DEFAULT_WEIGHTS[c],
        )
        for c in grading.CRITERIA
    ]


@router.put("/courses/{course_id}/criteria", response_model=list[CriterionOut])
def set_criteria(
    course_id: uuid.UUID, data: WeightsUpdate, db: DbSession, principal: CurrentPrincipal
):
    """Set the weights of a course. Criteria left out keep their current weight."""
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    unknown = set(data.weights) - set(grading.CRITERIA)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown criteria: {sorted(unknown)}"
        )
    if any(w < 0 or w > 100 for w in data.weights.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Weights must be 0-100")
    weights = {**grading.course_weights(db, course_id), **data.weights}
    if abs(sum(weights.values()) - 100) > 0.01:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Weights must sum to 100 (got {sum(weights.values()):g})",
        )
    existing = {
        row.criterion: row
        for row in db.scalars(
            select(GradingCriterion).where(GradingCriterion.course_id == course_id)
        )
    }
    for criterion, weight in data.weights.items():
        row = existing.get(criterion) or GradingCriterion(course_id=course_id, criterion=criterion)
        row.weight, row.updated_by = weight, principal.id
        db.add(row)
    db.commit()
    return get_criteria(course_id, db, principal)


# -- grades ----------------------------------------------------------------------------


@router.get("/grades/{project_id}", response_model=GradeOut | StudentGradeOut)
def get_grade(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Staff see the suggestion and its justification; the student only the final grade."""
    project = access.get_project_for(db, principal, project_id)
    if principal.is_admin or principal.is_faculty:
        return _grade_out(db, project)
    final = grading.final_grade(db, project.id)
    return StudentGradeOut(
        project_id=project.id,
        status=project.status,
        final_total=final.faculty_adjusted_total if final else None,
        graded_at=final.graded_at if final else None,
    )


@router.put("/grades/{project_id}", response_model=GradeOut)
def set_grade(project_id: uuid.UUID, data: GradeUpdate, db: DbSession, principal: CurrentPrincipal):
    """The faculty member's final grade. Differences from the suggestion are logged."""
    project = access.get_project_for(db, principal, project_id)
    access.require_project_staff(db, principal, project)
    suggestion = grading.project_suggestion(db, project)

    grade = grading.final_grade(db, project.id) or FinalGrade(project_id=project.id)
    previous = grade.faculty_adjusted_total
    grade.scores = suggestion.scores
    grade.weights = suggestion.weights
    grade.suggested_total = suggestion.suggested_total
    grade.faculty_adjusted_total = data.total
    grade.faculty_notes = data.notes
    grade.graded_by = principal.id
    grade.graded_at = grading.now_utc()
    db.add(grade)
    db.add(
        LearningLog(
            event_type="grade_adjustment",
            project_id=project.id,
            original_value={
                "suggested_total": suggestion.suggested_total,
                "coverage": suggestion.coverage,
                "scores": suggestion.scores,
                "weights": suggestion.weights,
                "previous_final": previous,
            },
            adjusted_value={"total": data.total},
            faculty_id=principal.id,
            notes=data.notes,
        )
    )
    project.status = ProjectStatus.graded
    sent = notify.notify(
        db,
        [project.student_id],
        "grade_final",
        f"اعتُمدت درجتك في «{project.title}»",
        f"الدرجة النهائية: {data.total:g} من 100.",
        project,
    )
    db.commit()
    notify.send_emails(sent)
    return _grade_out(db, project)


def _course_rows(db, course: Course) -> list[dict]:
    projects = db.scalars(
        select(Project).where(Project.course_id == course.id).order_by(Project.submitted_at)
    ).all()
    names = internal_http.lookup_users({p.student_id for p in projects})
    rows = []
    for project in projects:
        grade = _grade_out(db, project)
        student = names.get(str(project.student_id), {})
        rows.append(
            {
                "project_id": str(project.id),
                "student_id": str(project.student_id),
                "student_name": student.get("full_name"),
                "student_number": student.get("student_id"),
                "title": project.title,
                "status": project.status.value,
                "scores": {b.criterion: b.score for b in grade.breakdown},
                "suggested_total": grade.suggested_total,
                "coverage": grade.coverage,
                "final_total": grade.final_total,
                "faculty_notes": grade.faculty_notes,
                "alerts": len(grade.alerts),
            }
        )
    return rows


@router.get("/grades/course/{course_id}")
def course_grades(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    return {
        "course_id": str(course.id),
        "weights": grading.course_weights(db, course.id),
        "projects": _course_rows(db, course),
    }


@router.get("/reports/course/{course_id}/excel")
def course_excel(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    course = access.get_course(db, course_id)
    if not access.can_manage_course(principal, course):
        raise forbidden()
    content = grade_sheet(
        f"{course.code} - {course.name}",
        grading.course_weights(db, course.id),
        _course_rows(db, course),
    )
    filename = f"grades-{course.code}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
