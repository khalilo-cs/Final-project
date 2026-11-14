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
    "stack": {
        "languages": {"Python": 2},
        "technologies": [{"name": "Flask", "evidence": ["app.py"]}],
        "architecture": [],
    },
}


DB_ANALYZER_RESPONSE = {
    "total_tables": 2,
    "normalization_level": "2NF",
    "missing_primary_keys": ["logs"],
    "missing_foreign_keys": [],
    "missing_indexes": [],
    "query_issues": [],
    "er_diagram_mermaid": "erDiagram\n    users {\n        int id PK\n    }\n",
    "overall_db_score": 80.0,
}


REPORT_ANALYZER_RESPONSE = {
    "plagiarism": {
        "plagiarism_percentage": 42.0,
        "sources": [{"document_id": "", "similarity": 0.42, "reverse_similarity": 0.3}],
        "passages": [{"text": "copied text", "words": 30, "source": ""}],
    },
    "consistency": {
        "inconsistencies": [{"type": "claimed_not_found", "severity": "Medium"}],
        "checked": True,
    },
    "documentation": {"documentation_quality_score": 70.0},
    "overall_report_score": 61.5,
}


class Analyzer:
    """Fake code-analyzer + db-analyzer.

    Tests can change `status` / `body` (code) and `db_status` / `db_body` (database),
    and inspect `calls` / `db_calls`.
    """

    def __init__(self):
        self.status, self.body = 200, ANALYZER_RESPONSE
        self.db_status, self.db_body = 200, DB_ANALYZER_RESPONSE
        self.report_status, self.report_body = 200, REPORT_ANALYZER_RESPONSE
        self.calls: list[httpx.Request] = []
        self.db_calls: list[httpx.Request] = []
        self.report_calls: list[httpx.Request] = []
        self.forgotten: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/v1/documents/"):
            self.forgotten.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(204)
        if request.url.path == "/api/v1/analysis/report":
            self.report_calls.append(request)
            return httpx.Response(self.report_status, json=self.report_body)
        if request.url.path == "/api/v1/analysis/database":
            self.db_calls.append(request)
            return httpx.Response(self.db_status, json=self.db_body)
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
