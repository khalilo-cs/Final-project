import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    semester: str | None = Field(default=None, max_length=50)
    year: int | None = Field(default=None, ge=2000, le=2100)
    level: Literal["year1", "year2", "year3", "year4", "postgrad"] = "year4"
    kind: Literal["assignment", "course_project", "graduation"] = "graduation"
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
    level: str
    kind: str
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
    has_database: bool
    db_dialect: str | None
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
    stack: dict
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


class DbResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    total_tables: int
    normalization_level: str | None
    missing_primary_keys: list
    missing_foreign_keys: list
    missing_indexes: list
    query_issues: list
    overall_db_score: float
    details: dict
    analyzed_at: datetime


class ErDiagramOut(BaseModel):
    project_id: uuid.UUID
    format: str = "mermaid"
    diagram: str


class ReportResultOut(BaseModel):
    project_id: uuid.UUID
    plagiarism_percentage: float
    plagiarism_sources: list
    inconsistencies: list
    documentation_quality_score: float
    overall_report_score: float
    details: dict
    analyzed_at: datetime


class CriterionOut(BaseModel):
    criterion: str
    label_ar: str
    weight: float
    is_default: bool


class WeightsUpdate(BaseModel):
    weights: dict[str, float] = Field(description="criterion -> weight; must sum to 100")


class GradeBreakdown(BaseModel):
    criterion: str
    label_ar: str
    weight: float
    score: float | None
    points: float | None
    justification: str | None


class GradeOut(BaseModel):
    project_id: uuid.UUID
    status: ProjectStatus
    suggested_total: float | None
    coverage: float
    missing_criteria: list[str]
    cap_reason: str | None = None
    breakdown: list[GradeBreakdown]
    final_total: float | None
    faculty_notes: str | None
    graded_at: datetime | None
    alerts: list[dict]


class StudentGradeOut(BaseModel):
    """What a student sees: only the final decision, once it exists."""

    project_id: uuid.UUID
    status: ProjectStatus
    final_total: float | None
    graded_at: datetime | None


class GradeUpdate(BaseModel):
    total: float = Field(ge=0, le=100)
    notes: str | None = Field(default=None, max_length=5000)
