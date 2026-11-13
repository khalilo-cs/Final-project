"""Who may see or change what. Every rule lives here so routes stay thin."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course, Enrollment
from app.models.project import Project
from app.routes.deps import Principal, forbidden, not_found


def get_course(db: Session, course_id: uuid.UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise not_found("Course")
    return course


def is_enrolled(db: Session, student_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Enrollment.id).where(
                Enrollment.student_id == student_id, Enrollment.course_id == course_id
            )
        )
        is not None
    )


def can_manage_course(principal: Principal, course: Course) -> bool:
    return principal.is_admin or (principal.is_faculty and course.faculty_id == principal.id)


def require_course_view(db: Session, principal: Principal, course: Course) -> None:
    if can_manage_course(principal, course):
        return
    if principal.is_student and is_enrolled(db, principal.id, course.id):
        return
    raise forbidden()


def require_course_manage(principal: Principal, course: Course) -> None:
    if not can_manage_course(principal, course):
        raise forbidden()


def get_project_for(db: Session, principal: Principal, project_id: uuid.UUID) -> Project:
    """Load a project the principal may see. Unauthorized looks like missing."""
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project")
    if principal.is_admin or project.student_id == principal.id:
        return project
    if principal.is_faculty and db.get(Course, project.course_id).faculty_id == principal.id:
        return project
    raise not_found("Project")


def require_project_staff(db: Session, principal: Principal, project: Project) -> None:
    """Admin or the course's faculty member."""
    if not can_manage_course(principal, db.get(Course, project.course_id)):
        raise forbidden()
