import io
import os
import subprocess
import time
import zipfile
from pathlib import Path

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.config import get_settings


def token(role="service"):
    payload = {"sub": "svc", "role": role, "type": "access", "exp": time.time() + 60}
    return {"Authorization": "Bearer " + jwt.encode(payload, get_settings().jwt_secret, "HS256")}


def zip_dir(root: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(root).as_posix())
    return buffer.getvalue()


def zip_files(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def git(repo: Path, *args, date: str | None = None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Sara", "GIT_AUTHOR_EMAIL": "sara@example.com",
           "GIT_COMMITTER_NAME": "Sara", "GIT_COMMITTER_EMAIL": "sara@example.com"}  # fmt: skip
    if date:
        env |= {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                   cwd=repo, env=env, check=True, capture_output=True)  # fmt: skip


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(database, "engine", engine)
    database.SessionLocal.configure(bind=engine)
    from app import main

    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()


def analyze(client, document_id, data, exclude=(), index=True):
    import json

    response = client.post(
        "/api/v1/fraud/analyze",
        files={"file": ("code.zip", data, "application/zip")},
        data={
            "document_id": document_id,
            "exclude_ids": json.dumps(list(exclude)),
            "index": str(index).lower(),
        },  # fmt: skip
        headers=token(),
    )
    assert response.status_code == 200, response.text
    return response.json()
