import io
import re
import uuid
import zipfile
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.models.project import Project
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.services import access, internal_http, student_report

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _pdf(content: bytes, filename: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/student/{project_id}/pdf")
def student_pdf(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Staff get the full report; the student gets feedback without suspicion or suggestion."""
    project = access.get_project_for(db, principal, project_id)
    audience = "student" if project.student_id == principal.id else "staff"
    if audience == "staff":
        access.require_project_staff(db, principal, project)
    try:
        content = student_report.render(student_report.build_payload(db, project, audience))
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Report generator unavailable"
        ) from exc
    return _pdf(content, f"report-{project_id}.pdf")


@router.get("/course/{course_id}/pdf.zip")
def course_pdfs(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Every project's full report for a course, in one ZIP (staff)."""
    course = access.get_course(db, course_id)
    if not access.can_manage_course(principal, course):
        raise forbidden()
    projects = db.scalars(select(Project).where(Project.course_id == course_id)).all()
    names = internal_http.lookup_users({p.student_id for p in projects})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for project in projects:
            student = names.get(str(project.student_id), {})
            label = student.get("student_id") or student.get("full_name") or str(project.id)[:8]
            safe = re.sub(r"[^\w\-]+", "_", label)
            try:
                content = student_report.render(
                    student_report.build_payload(db, project, "staff", names)
                )
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, "Report generator unavailable"
                ) from exc
            bundle.writestr(f"{safe}-{str(project.id)[:8]}.pdf", content)
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=reports-{course.code}.zip"},
    )
