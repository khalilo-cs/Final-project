import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.course import Course, Enrollment
from app.models.project import Project
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.routes.projects import to_out
from app.schemas.schemas import CourseCreate, CourseOut, EnrollRequest, ProjectOut
from app.services import access

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


@router.get("", response_model=list[CourseOut])
def list_courses(db: DbSession, principal: CurrentPrincipal):
    query = select(Course).order_by(Course.code)
    if principal.is_faculty:
        query = query.where(Course.faculty_id == principal.id)
    elif principal.is_student:
        query = query.join(Enrollment).where(Enrollment.student_id == principal.id)
    elif not principal.is_admin:
        raise forbidden()
    return db.scalars(query).all()


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(data: CourseCreate, db: DbSession, principal: CurrentPrincipal):
    if principal.is_admin:
        if data.faculty_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "faculty_id is required")
        faculty_id = data.faculty_id
    elif principal.is_faculty:
        if data.faculty_id not in (None, principal.id):
            raise forbidden()
        faculty_id = principal.id
    else:
        raise forbidden()

    course = Course(**data.model_dump(exclude={"faculty_id"}), faculty_id=faculty_id)
    db.add(course)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Course code already exists") from exc
    return course


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    course = access.get_course(db, course_id)
    access.require_course_view(db, principal, course)
    return course


@router.get("/{course_id}/students", response_model=list[uuid.UUID])
def list_students(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    return db.scalars(select(Enrollment.student_id).where(Enrollment.course_id == course_id)).all()


@router.post("/{course_id}/students", response_model=list[uuid.UUID])
def enroll_students(
    course_id: uuid.UUID, data: EnrollRequest, db: DbSession, principal: CurrentPrincipal
):
    """Enroll students (idempotent). Returns the full list of enrolled students."""
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    existing = set(
        db.scalars(select(Enrollment.student_id).where(Enrollment.course_id == course_id))
    )
    for student_id in dict.fromkeys(data.student_ids):
        if student_id not in existing:
            db.add(Enrollment(student_id=student_id, course_id=course_id))
            existing.add(student_id)
    db.commit()
    return sorted(existing)


@router.delete("/{course_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def unenroll_student(
    course_id: uuid.UUID, student_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
):
    course = access.get_course(db, course_id)
    access.require_course_manage(principal, course)
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.student_id == student_id
        )
    )
    if enrollment is not None:
        db.delete(enrollment)
        db.commit()


@router.get("/{course_id}/projects", response_model=list[ProjectOut])
def list_course_projects(course_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    course = access.get_course(db, course_id)
    query = select(Project).where(Project.course_id == course_id).order_by(Project.submitted_at)
    if not access.can_manage_course(principal, course):
        access.require_course_view(db, principal, course)
        query = query.where(Project.student_id == principal.id)
    return [to_out(project) for project in db.scalars(query)]
