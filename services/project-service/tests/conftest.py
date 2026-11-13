import os
import time
import uuid

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.config import get_settings
from app.services import analysis_runner

ANALYZER_RESPONSE = {
    "code": {
        "total_files": 2,
        "total_lines": 40,
        "total_classes": 1,
        "total_functions": 3,
        "languages": {"python": 2},
        "cyclomatic_complexity_avg": 2.5,
        "cognitive_complexity_avg": 1.0,
        "code_smells": [],
        "overall_quality_score": 95.0,
    },
    "security": {
        "vulnerabilities": [{"type": "SQL Injection", "severity": "Critical", "line": 3}],
        "critical_count": 1,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "overall_security_score": 75.0,
    },
}


class Analyzer:
    """Fake code-analyzer; tests can change `status` / `body` or inspect `calls`."""

    def __init__(self):
        self.status = 200
        self.body = ANALYZER_RESPONSE
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(self.status, json=self.body)


@pytest.fixture
def analyzer(monkeypatch):
    fake = Analyzer()
    monkeypatch.setattr(analysis_runner, "transport", httpx.MockTransport(fake))
    return fake


@pytest.fixture
def client(monkeypatch, tmp_path, analyzer):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(database, "engine", engine)
    database.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path / "storage"))

    from app import main

    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()


class User:
    def __init__(self, role: str):
        self.id = uuid.uuid4()
        self.role = role

    @property
    def headers(self) -> dict:
        payload = {
            "sub": str(self.id),
            "role": self.role,
            "type": "access",
            "exp": time.time() + 300,
        }
        token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def users():
    return {
        "admin": User("admin"),
        "faculty": User("faculty"),
        "other_faculty": User("faculty"),
        "student": User("student"),
        "other_student": User("student"),
    }
