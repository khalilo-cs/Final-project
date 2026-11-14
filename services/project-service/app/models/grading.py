import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.course import now


class GradingCriterion(Base):
    """A course's weight for one criterion (overrides the defaults)."""

    __tablename__ = "grading_criteria"
    __table_args__ = (UniqueConstraint("course_id", "criterion"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    criterion: Mapped[str] = mapped_column(String(50))
    weight: Mapped[float] = mapped_column(Float)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinalGrade(Base):
    """The faculty member's decision, with the system's suggestion at that moment."""

    __tablename__ = "final_grades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    scores: Mapped[dict] = mapped_column(JSON)  # criterion -> score (0-100) or null
    weights: Mapped[dict] = mapped_column(JSON)
    suggested_total: Mapped[float | None] = mapped_column(Float)
    faculty_adjusted_total: Mapped[float] = mapped_column(Float)
    faculty_notes: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LearningLog(Base):
    """Every faculty correction of the system, for tuning weights later (plan phase 8)."""

    __tablename__ = "learning_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(50))  # grade_adjustment, ...
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    original_value: Mapped[dict] = mapped_column(JSON)
    adjusted_value: Mapped[dict] = mapped_column(JSON)
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
