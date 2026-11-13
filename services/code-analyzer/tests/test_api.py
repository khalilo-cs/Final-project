import io
import stat
import time
import zipfile

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)

VULNERABLE = """
import sqlite3

API_KEY = "9f8a7b6c5d4e3f2a1b0c"

def find_user(name):
    conn = sqlite3.connect("app.db")
    return conn.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchall()
"""
CLEAN = "def add(a, b):\n    return a + b\n"


def token(token_type="access", secret=None, lifetime=300):
    payload = {
        "sub": "user-1",
        "role": "faculty",
        "type": token_type,
        "exp": time.time() + lifetime,
    }
    return jwt.encode(payload, secret or get_settings().jwt_secret, algorithm="HS256")


def auth(**kwargs):
    return {"Authorization": f"Bearer {token(**kwargs)}"}


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def upload(data: bytes, headers=None):
    return client.post(
        "/api/v1/analysis/code",
        files={"file": ("project.zip", data, "application/zip")},
        headers=auth() if headers is None else headers,
    )


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "code-analyzer"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer nonsense"},
        auth(token_type="refresh"),
        auth(secret="another-secret-another-secret-another-1"),
        auth(lifetime=-10),
    ],
)
def test_requires_valid_access_token(headers):
    assert upload(make_zip({"a.py": CLEAN}), headers=headers).status_code == 401


def test_full_analysis():
    archive = make_zip(
        {
            "src/app.py": VULNERABLE,
            "src/util.py": CLEAN,
            "node_modules/lib/skip.py": VULNERABLE,
            "venv/lib/skip.py": VULNERABLE,
            "README.md": "# demo",
        }
    )
    response = upload(archive)
    assert response.status_code == 200
    body = response.json()

    code = body["code"]
    assert code["total_files"] == 2
    assert code["total_functions"] == 2
    assert code["languages"] == {"python": 2}
    assert code["overall_quality_score"] == 100.0
    assert {f["path"] for f in code["files"]} == {"src/app.py", "src/util.py"}

    security = body["security"]
    assert [(v["type"], v["file"]) for v in security["vulnerabilities"]] == [
        ("SQL Injection", "src/app.py"),
        ("Hardcoded Secret", "src/app.py"),
    ]
    assert (security["critical_count"], security["high_count"]) == (1, 1)
    assert security["overall_security_score"] == 60.0
    assert "9f8a7b6c5d4e3f2a1b0c" not in response.text


def test_rejects_non_zip():
    response = upload(b"definitely not a zip")
    assert response.status_code == 400


def test_rejects_zip_slip():
    response = upload(make_zip({"../../evil.py": CLEAN}))
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]


def test_symlinks_are_not_extracted():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        link = zipfile.ZipInfo("passwd.py")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(link, "/etc/passwd")
        bundle.writestr("ok.py", CLEAN)
    body = upload(buffer.getvalue()).json()
    assert [f["path"] for f in body["code"]["files"]] == ["ok.py"]


def test_limits(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_files", 2)
    too_many = make_zip({f"f{i}.py": CLEAN for i in range(3)})
    assert upload(too_many).status_code == 400

    monkeypatch.setattr(settings, "max_files", 5000)
    monkeypatch.setattr(settings, "max_extracted_mb", 1)
    bomb = make_zip({"big.py": "#" * (2 * 1024 * 1024)})
    assert upload(bomb).status_code == 400

    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert upload(make_zip({"a.py": CLEAN})).status_code == 413
