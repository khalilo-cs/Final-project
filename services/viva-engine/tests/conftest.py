import os
import time
import uuid

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.config import get_settings
from app.engine import dialogue

CONTEXT = {
    "title": "نظام إدارة المكتبة",
    "languages": {"Python": 4},
    "technologies": ["Flask", "MySQL"],
    "architecture": ["MVC"],
    "functions": [
        {
            "file": "app/loans.py",
            "function": "LoanService.calculate_fine",
            "line": 10,
            "end_line": 40,
            "cyclomatic_complexity": 9,
            "calls": ["days_late", "get_rate"],
            "code": "def calculate_fine(loan):\n    days = days_late(loan)\n    ...",
        }
    ],
    "vulnerabilities": [
        {"type": "SQL Injection", "file": "app/db.py", "line": 22, "evidence": "cur.execute(f'...')"}
    ],
    "database": {
        "tables": [
            {"name": "books", "primary_key": ["id"], "foreign_keys": []},
            {"name": "loans", "primary_key": ["id"],
             "foreign_keys": [{"columns": ["book_id"], "ref_table": "books"}]},
        ],
        "normalization_level": "3NF",
        "issues": [],
    },
    "report": {"inconsistencies": []},
}  # fmt: skip


def token(sub, role):
    payload = {"sub": str(sub), "role": role, "type": "access", "exp": time.time() + 300}
    return {"Authorization": "Bearer " + jwt.encode(payload, get_settings().jwt_secret, "HS256")}


@pytest.fixture(autouse=True)
def no_external_models(monkeypatch):
    """By default only the built-in engine runs; tests add fake models explicitly."""
    monkeypatch.setattr(dialogue, "PROVIDERS", [])


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


@pytest.fixture
def people():
    return {"student": uuid.uuid4(), "faculty": uuid.uuid4(), "other": uuid.uuid4()}


@pytest.fixture
def started(client, people):
    """A viva started the way project-service starts it."""
    body = {
        "project_id": str(uuid.uuid4()),
        "student_id": str(people["student"]),
        "staff_ids": [str(people["faculty"])],
        "language": "ar",
        "context": CONTEXT,
    }
    response = client.post("/internal/sessions", json=body, headers=token("svc", "service"))
    assert response.status_code == 201, response.text
    return response.json()
