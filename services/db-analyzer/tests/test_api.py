import time

import jwt
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def headers(token_type="access"):
    payload = {"sub": "u", "role": "faculty", "type": token_type, "exp": time.time() + 60}
    token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def post(data: bytes, auth=None, **form):
    return client.post(
        "/api/v1/analysis/database",
        files={"file": ("schema.sql", data, "text/plain")},
        data=form,
        headers=headers() if auth is None else auth,
    )


def test_health():
    assert client.get("/health").json()["service"] == "db-analyzer"


def test_requires_access_token():
    assert post(b"SELECT 1;", auth={}).status_code == 401
    assert post(b"SELECT 1;", auth=headers("refresh")).status_code == 401


def test_analyze_upload():
    body = post("﻿CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(10));".encode()).json()
    assert body["total_tables"] == 1 and body["dialect"] == "mysql"


def test_dialect_and_validation(monkeypatch):
    assert post(b"CREATE TABLE t (id INT);", dialect="postgresql").json()["dialect"] == (
        "postgresql"
    )
    assert post(b"x", dialect="oracle").status_code == 422
    assert post(b"\x00\x01binary").status_code == 400
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    assert post(b"SELECT 1;").status_code == 413
