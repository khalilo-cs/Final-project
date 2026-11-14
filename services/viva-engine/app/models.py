import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now() -> datetime:
    return datetime.now(UTC)


class VivaSession(Base):
    __tablename__ = "viva_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    staff_ids: Mapped[list] = mapped_column(JSON, default=list)  # who may review it
    language: Mapped[str] = mapped_column(String(2), default="ar")
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    level: Mapped[int] = mapped_column(Integer, default=1)
    context: Mapped[dict] = mapped_column(JSON)  # project facts from project-service
    pool: Mapped[list] = mapped_column(JSON, default=list)  # candidate questions
    current: Mapped[dict | None] = mapped_column(JSON)  # question awaiting an answer
    providers: Mapped[list] = mapped_column(JSON, default=list)
    overall_score: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VivaQA(Base):
    __tablename__ = "viva_qa"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("viva_sessions.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    template_key: Mapped[str] = mapped_column(String(80), index=True)
    question_type: Mapped[str] = mapped_column(String(20))
    level: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30))  # which provider wrote the question
    question: Mapped[str] = mapped_column(Text)
    expected_points: Mapped[list] = mapped_column(JSON, default=list)
    related_file: Mapped[str | None] = mapped_column(String(500))
    related_lines: Mapped[str | None] = mapped_column(String(50))
    answer: Mapped[str] = mapped_column(Text)
    provider_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # provider -> score
    score: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text)
    response_seconds: Mapped[float | None] = mapped_column(Float)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Review(Base):
    """A faculty member's correction of one evaluated answer: the system learns from it."""

    __tablename__ = "viva_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    qa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("viva_qa.id", ondelete="CASCADE"), unique=True
    )
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    score: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(30), index=True)  # web, reviewed_qa, ...
    source_ref: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    items: Mapped[int] = mapped_column(Integer, default=0)
    added_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Topic(Base):
    """Something the system knows (or must learn) about: a technology, vulnerability..."""

    __tablename__ = "topics"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)  # e.g. tech:flask
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(30))  # builtin, project
    seen_in_projects: Mapped[int] = mapped_column(Integer, default=0)
    docs_status: Mapped[str] = mapped_column(String(20), default="none")  # pending/done/none
    teacher_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending/done/skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    learned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankQuestion(Base):
    """A reusable viva question about a topic (built-in or taught by a model)."""

    __tablename__ = "question_bank"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(100), index=True)
    language: Mapped[str] = mapped_column(String(2))
    question_type: Mapped[str] = mapped_column(String(20))
    level: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    expected_points: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(40))  # builtin, teacher:claude, ...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AutoLabel(Base):
    """A grade several independent graders agreed on: learned without a professor."""

    __tablename__ = "auto_labels"

    qa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("viva_qa.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(20))
    agreement: Mapped[float] = mapped_column(Float)


class LearnedPoint(Base):
    """A key point the system discovered from strong answers to a question."""

    __tablename__ = "learned_points"

    template_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    point: Mapped[str] = mapped_column(String(100), primary_key=True)
    support: Mapped[int] = mapped_column(Integer)


class LearningEvent(Base):
    __tablename__ = "learning_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(30))  # project, session, web, teacher, builtin
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
