from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CodeDocument(Base):
    __tablename__ = "code_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # project id
    files: Mapped[int] = mapped_column(Integer)
    fingerprint_count: Mapped[int] = mapped_column(Integer)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CodeFingerprint(Base):
    __tablename__ = "code_fingerprints"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("code_documents.id", ondelete="CASCADE"), primary_key=True
    )
    hash: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    file: Mapped[str] = mapped_column(String(500))  # first place it occurs
    line: Mapped[int] = mapped_column(Integer)
