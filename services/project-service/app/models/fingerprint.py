import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.course import now


class ComprehensionChallenge(Base):
    """One defect seeded into the student's own function (the comprehension fingerprint).

    `answer` holds the original line and is never sent to the student before they answer.
    """

    __tablename__ = "comprehension_challenges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    file: Mapped[str] = mapped_column(String(500))
    function: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(30))
    start_line: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(Text)  # the function with the defect
    answer: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chosen_line: Mapped[int | None] = mapped_column(Integer)
    fixed_line: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    located: Mapped[bool | None] = mapped_column(Boolean)
    fixed: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    seconds: Mapped[int | None] = mapped_column(Integer)
    # Times the page lost focus while the challenge was open (looking elsewhere).
    focus_losses: Mapped[int] = mapped_column(Integer, default=0)
