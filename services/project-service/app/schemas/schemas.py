import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    semester: str | None = Field(default=None, max_length=50)
    year: int | None = Field(default=None, ge=2000, le=2100)
    # Admins may create a course on behalf of a faculty member.
    faculty_id: uuid.UUID | None = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    faculty_id: uuid.UUID
    semester: str | None
    year: int | None
    created_at: datetime


class EnrollRequest(BaseModel):
    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    student_id: uuid.UUID
    course_id: uuid.UUID
    programming_languages: list[str]
    frameworks: list[str]
    git_url: str | None
    has_report: bool
    status: ProjectStatus
    analysis_error: str | None
    submitted_at: datetime
    updated_at: datetime


class ProjectStatusOut(BaseModel):
    id: uuid.UUID
    status: ProjectStatus
    analysis_error: str | None
    updated_at: datetime


class CodeResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    total_files: int
    total_lines: int
    total_classes: int
    total_functions: int
    cyclomatic_complexity_avg: float
    cognitive_complexity_avg: float
    code_smells: list
    overall_quality_score: float
    details: dict
    analyzed_at: datetime


class SecurityResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    vulnerabilities: list
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    overall_security_score: float
    analyzed_at: datetime
