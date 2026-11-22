import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.models.project import Project, ProjectStatus
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.schemas.schemas import ProjectOut, ProjectStatusOut
from app.services import access, notify, storage, uploads
from app.services.analysis_runner import forget_report, run_analysis

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

_NAMES = TypeAdapter(list[str])


def to_out(project: Project) -> ProjectOut:
    return ProjectOut.model_validate(project, from_attributes=True)


def _name_list(raw: str | None, field: str) -> list[str]:
    """Accept a JSON array or a comma-separated list."""
    if not raw:
        return []
    try:
        values = json.loads(raw) if raw.lstrip().startswith("[") else raw.split(",")
        names = [name.strip() for name in _NAMES.validate_python(values) if name.strip()]
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} must be a list of names"
        ) from exc
    if len(names) > 20 or any(len(name) > 50 for name in names):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} is too long")
    return list(dict.fromkeys(names))


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def submit_project(
    db: DbSession,
    principal: CurrentPrincipal,
    background: BackgroundTasks,
    title: Annotated[str, Form(min_length=1, max_length=500)],
    course_id: Annotated[uuid.UUID, Form()],
    code: Annotated[UploadFile | None, File(description="Source code as a ZIP archive")] = None,
    report: Annotated[UploadFile | None, File(description="Report (PDF or DOCX)")] = None,
    database: Annotated[
        UploadFile | None,
        File(description="Database schema / dump (.sql) or MongoDB export (.json)"),
    ] = None,
    db_dialect: Annotated[Literal["mysql", "postgresql", "sqlite", "mongodb"], Form()] = "mysql",
    description: Annotated[str | None, Form(max_length=10_000)] = None,
    programming_languages: Annotated[str | None, Form()] = None,
    frameworks: Annotated[str | None, Form()] = None,
    git_url: Annotated[str | None, Form(max_length=500, pattern=r"^https://\S+$")] = None,
    # Files sent beforehand through /api/v1/uploads (weak connections), instead of above.
    code_upload_id: Annotated[uuid.UUID | None, Form()] = None,
    report_upload_id: Annotated[uuid.UUID | None, Form()] = None,
    database_upload_id: Annotated[uuid.UUID | None, Form()] = None,
):
    """A student submits a project for a course they are enrolled in.

    Code (and database, when a .sql file is given) analysis starts automatically;
    poll `GET /projects/{id}/status`.
    """
    if not principal.is_student:
        raise forbidden()
    access.get_course(db, course_id)
    if not access.is_enrolled(db, principal.id, course_id):
        raise forbidden()

    settings = get_settings()
    project_id = uuid.uuid4()
    folder = storage.project_dir(project_id)
    try:
        code_path = folder / "code.zip"
        if code_upload_id is not None:
            uploads.claim(db, principal.id, code_upload_id, "code", code_path)
        elif code is not None and code.filename:
            storage.save_upload(code, code_path, settings.max_code_mb, storage.ZIP_MAGIC)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The code ZIP is required")
        report_path = None
        if report_upload_id is not None:
            name = uploads.get_own(db, principal.id, report_upload_id).filename
            report_path = folder / f"report{storage.report_extension(name)}"
            uploads.claim(db, principal.id, report_upload_id, "report", report_path)
        elif report is not None and report.filename:
            extension = storage.report_extension(report.filename)
            report_path = folder / f"report{extension}"
            storage.save_upload(
                report,
                report_path,
                settings.max_report_mb,
                (storage.REPORT_EXTENSIONS[extension],),
            )
        db_schema_path = None
        db_name = None
        if database_upload_id is not None:
            db_name = uploads.get_own(db, principal.id, database_upload_id).filename
            db_schema_path = folder / "schema.sql"
            uploads.claim(db, principal.id, database_upload_id, "database", db_schema_path)
        elif database is not None and database.filename:
            db_name = database.filename
            storage.require_extension(database.filename, {".sql", ".json"}, "Database file")
            db_schema_path = folder / "schema.sql"
            storage.save_upload(database, db_schema_path, settings.max_sql_mb, None)
        if db_name and db_name.lower().endswith(".json"):
            db_dialect = "mongodb"  # a JSON export can only be a MongoDB schema
        project = Project(
            id=project_id,
            title=title.strip(),
            description=description,
            student_id=principal.id,
            course_id=course_id,
            programming_languages=_name_list(programming_languages, "programming_languages"),
            frameworks=_name_list(frameworks, "frameworks"),
            git_url=git_url,
            code_path=str(code_path),
            report_path=str(report_path) if report_path else None,
            db_schema_path=str(db_schema_path) if db_schema_path else None,
            db_dialect=db_dialect if db_schema_path else None,
            status=ProjectStatus.analyzing,
        )
        db.add(project)
        sent = notify.notify(
            db,
            notify.course_faculty(db, course_id),
            "new_submission",
            f"مشروع جديد: {project.title}",
            "سلّم طالب مشروعاً جديداً، والتحليل جارٍ الآن.",
            project,
        )
        db.commit()
    except BaseException:
        db.rollback()
        storage.delete_project_files(project_id)
        raise

    uploads.discard([code_upload_id, report_upload_id, database_upload_id])
    notify.send_emails(sent)
    background.add_task(run_analysis, project_id)
    return to_out(project)


@router.get("", response_model=list[ProjectOut])
def my_projects(db: DbSession, principal: CurrentPrincipal):
    """The current student's own projects."""
    query = select(Project).where(Project.student_id == principal.id)
    return [to_out(project) for project in db.scalars(query.order_by(Project.submitted_at))]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    return to_out(access.get_project_for(db, principal, project_id))


@router.get("/{project_id}/status", response_model=ProjectStatusOut)
def get_status(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    project = access.get_project_for(db, principal, project_id)
    return ProjectStatusOut(
        id=project.id,
        status=project.status,
        analysis_error=project.analysis_error,
        updated_at=project.updated_at,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, background: BackgroundTasks
):
    """Students may withdraw a submission until it is graded; staff may always delete."""
    project = access.get_project_for(db, principal, project_id)
    is_owner = project.student_id == principal.id
    if is_owner and not principal.is_admin and project.status is ProjectStatus.graded:
        raise HTTPException(status.HTTP_409_CONFLICT, "Graded projects cannot be withdrawn")
    if not is_owner:
        access.require_project_staff(db, principal, project)
    db.delete(project)
    db.commit()
    storage.delete_project_files(project_id)
    background.add_task(forget_report, project_id)
