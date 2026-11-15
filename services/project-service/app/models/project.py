import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.course import now


class ProjectStatus(enum.StrEnum):
    submitted = "submitted"
    analyzing = "analyzing"
    analyzed = "analyzed"
    analysis_failed = "analysis_failed"
    viva_scheduled = "viva_scheduled"
    viva_completed = "viva_completed"
    graded = "graded"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    programming_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    frameworks: Mapped[list[str]] = mapped_column(JSON, default=list)
    git_url: Mapped[str | None] = mapped_column(String(500))
    code_path: Mapped[str] = mapped_column(String(500))
    report_path: Mapped[str | None] = mapped_column(String(500))
    # The code exactly as first submitted, kept once AI fixes change code_path.
    original_code_path: Mapped[str | None] = mapped_column(String(500))
    db_schema_path: Mapped[str | None] = mapped_column(String(500))
    db_dialect: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.submitted
    )
    analysis_error: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    @property
    def has_report(self) -> bool:
        return self.report_path is not None

    @property
    def has_database(self) -> bool:
        return self.db_schema_path is not None


class CodeAnalysisResult(Base):
    __tablename__ = "code_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    total_files: Mapped[int] = mapped_column(Integer)
    total_lines: Mapped[int] = mapped_column(Integer)
    total_classes: Mapped[int] = mapped_column(Integer)
    total_functions: Mapped[int] = mapped_column(Integer)
    cyclomatic_complexity_avg: Mapped[float] = mapped_column(Float)
    cognitive_complexity_avg: Mapped[float] = mapped_column(Float)
    code_smells: Mapped[list] = mapped_column(JSON)
    overall_quality_score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)  # full analyzer output
    # Languages, frameworks and architecture actually found in the code.
    stack: Mapped[dict] = mapped_column(JSON, default=dict)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SecurityAnalysisResult(Base):
    __tablename__ = "security_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    vulnerabilities: Mapped[list] = mapped_column(JSON)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    overall_security_score: Mapped[float] = mapped_column(Float)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DbAnalysisResult(Base):
    __tablename__ = "db_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    total_tables: Mapped[int] = mapped_column(Integer)
    normalization_level: Mapped[str | None] = mapped_column(String(10))
    missing_primary_keys: Mapped[list] = mapped_column(JSON)
    missing_foreign_keys: Mapped[list] = mapped_column(JSON)
    missing_indexes: Mapped[list] = mapped_column(JSON)
    query_issues: Mapped[list] = mapped_column(JSON)
    er_diagram: Mapped[str] = mapped_column(Text)  # Mermaid erDiagram source
    overall_db_score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)  # full analyzer output
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReportAnalysisResult(Base):
    __tablename__ = "report_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    plagiarism_percentage: Mapped[float] = mapped_column(Float)
    plagiarism_sources: Mapped[list] = mapped_column(JSON)
    inconsistencies: Mapped[list] = mapped_column(JSON)
    documentation_quality_score: Mapped[float] = mapped_column(Float)
    overall_report_score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)  # full analyzer output
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiFixLog(Base):
    """A fix the AI applied with the student's approval (shown to faculty)."""

    __tablename__ = "ai_fix_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    fix_id: Mapped[str] = mapped_column(String(20))
    file: Mapped[str] = mapped_column(String(500))
    line: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    approved_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VivaLink(Base):
    """A viva session run by viva-engine for this project."""

    __tablename__ = "viva_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    score: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FraudResult(Base):
    """Raw evidence from fraud-detector; the authenticity score is computed from it."""

    __tablename__ = "fraud_detection_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    code_similarity_max: Mapped[float] = mapped_column(Float)
    similar_projects: Mapped[list] = mapped_column(JSON)
    git_analysis: Mapped[dict | None] = mapped_column(JSON)
    style: Mapped[dict] = mapped_column(JSON)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PerformanceResult(Base):
    """A sandbox run of the project (runs in the background on sandbox-runner)."""

    __tablename__ = "performance_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    run_id: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # running, done, unavailable, lost
    runs_successfully: Mapped[bool | None] = mapped_column()
    overall_performance_score: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
