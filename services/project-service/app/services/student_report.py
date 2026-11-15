"""Collect everything about a project into the payload report-generator turns into a PDF."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.course import Course
from app.models.project import AiFixLog, Project
from app.services import grading, internal_http
from app.services.advisor import build_advice


def _row(obj, *fields) -> dict | None:
    if obj is None:
        return None
    return {field: getattr(obj, field) for field in fields}


def _code(code) -> dict | None:
    if code is None:
        return None
    row = _row(code, "total_files", "total_lines", "total_classes", "total_functions",
               "cyclomatic_complexity_avg")  # fmt: skip
    return {**row, "details": {**code.details, "stack": code.stack}}


def build_payload(db: Session, project: Project, audience: str, names: dict | None = None) -> dict:
    results = grading.load_results(db, project.id)
    suggestion = grading.suggest(grading.course_weights(db, project.course_id), results)
    final = grading.final_grade(db, project.id)
    course = db.get(Course, project.course_id)
    if names is None:
        names = internal_http.lookup_users({project.student_id})
    student = names.get(str(project.student_id), {})
    viva = grading.latest_viva(db, project.id)
    perf = results.performance
    return {
        "audience": audience,
        "project": {"title": project.title, "status": project.status.value},
        "student": {"name": student.get("full_name"), "number": student.get("student_id")},
        "course": f"{course.code} - {course.name}" if course else "",
        "grade": {
            "suggested_total": suggestion.suggested_total if audience == "staff" else None,
            "coverage": suggestion.coverage,
            "breakdown": suggestion.breakdown,
            "final_total": final.faculty_adjusted_total if final else None,
            "faculty_notes": final.faculty_notes if final else None,
        },
        "advice": build_advice(results),
        "code": _code(results.code),
        "security": _row(results.security, "vulnerabilities", "overall_security_score"),
        "database": _row(results.database, "total_tables", "normalization_level", "details",
                         "overall_db_score"),
        "report": _row(results.report, "plagiarism_percentage", "inconsistencies",
                       "documentation_quality_score"),
        "viva": {"score": viva.score, "status": viva.status} if viva else None,
        "performance": _row(perf, "status", "runs_successfully", "error", "details")
        if perf else None,
        "authenticity": results.authenticity if audience == "staff" else None,
        "applied_fixes": [
            {"file": f.file, "line": f.line, "title": f.title}
            for f in db.scalars(select(AiFixLog).where(AiFixLog.project_id == project.id))
        ],
    }  # fmt: skip


def render(payload: dict) -> bytes:
    return internal_http.post_bytes(
        get_settings().report_generator_url, "/internal/reports/student", payload
    )
