import io
import os
import time

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"

import jwt
import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.config import get_settings


def make_docx(sections: list[tuple[str, list[str]]], images: int = 0) -> bytes:
    """sections: [(heading, [paragraph, ...]), ...]"""
    document = Document()
    for heading, paragraphs in sections:
        document.add_heading(heading, level=1)
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf(lines: list[str]) -> bytes:
    """A minimal valid one-page PDF with Helvetica text (ASCII only)."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    body = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({t}) Tj T*" for t in escaped) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for number, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n{obj}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def token(role="service", token_type="access"):
    payload = {"sub": "svc", "role": role, "type": token_type, "exp": time.time() + 60}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


@pytest.fixture
def db_engine(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(database, "engine", engine)
    database.SessionLocal.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    with database.SessionLocal() as session:
        yield session


@pytest.fixture
def client(db_engine, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "engine", db_engine)
    with TestClient(main.app) as test_client:
        yield test_client
