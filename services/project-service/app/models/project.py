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
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.submitted
    )
    analysis_error: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    @property
    def has_report(self) -> bool:
        return self.report_path is not None


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
