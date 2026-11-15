import io
import json
import time
import zipfile
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from app import runner
from app.config import get_settings
from app.routes import runs
from app.sandbox.detect import UnsupportedProject, detect
from tests.fake_backend import FakeBackend


def tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(content)
    return tmp_path


# ---- stack detection -----------------------------------------------------------------


def test_detect_flask_inside_a_folder(tmp_path):
    plan = detect(tree(tmp_path, {
        "library/requirements.txt": "Flask==3.0\nPyMySQL\n",
        "library/app.py": "from flask import Flask\nserver = Flask(__name__)\n",
    }))  # fmt: skip
    assert (plan.stack, plan.workdir) == ("flask", "library")
    assert plan.start == "flask --app app:server run --host 0.0.0.0 --port 8000"
    assert plan.build[0] == "pip install --no-cache-dir -r library/requirements.txt"


@pytest.mark.parametrize(
    ("files", "stack", "start_contains"),
    [
        ({"main.py": "from fastapi import FastAPI\napi = FastAPI()\n"}, "fastapi", "main:api"),
        ({"manage.py": "", "requirements.txt": "django"}, "django", "runserver"),
        (
            {"package.json": json.dumps({"scripts": {"start": "node server.js"}})},
            "node",
            "npm start",
        ),
        ({"package.json": json.dumps({"dependencies": {"vite": "5"}})}, "node-frontend", "serve"),
        ({"index.php": "<?php echo 1;"}, "php", "php -S"),
        ({"pom.xml": "<project/>"}, "java-maven", "java -jar"),
        ({"site/index.html": "<h1>hi</h1>"}, "static", "http.server"),
    ],
)
def test_detect_stacks(tmp_path, files, stack, start_contains):
    plan = detect(tree(tmp_path, files))
    assert plan.stack == stack and start_contains in plan.start


def test_unsupported_project(tmp_path):
    with pytest.raises(UnsupportedProject):
        detect(tree(tmp_path, {"notes.txt": "hello"}))


# ---- runs with real HTTP against a local stand-in --------------------------------------

FLASK = {"requirements.txt": "flask\n", "app.py": "app = Flask(__name__)\n"}


def run(tmp_path, mode):
    project = tree(tmp_path / "p", FLASK)
    run_id = runner.new_run()
    backend = FakeBackend(mode)
    runner.execute(run_id, project, backend)
    assert backend.cleaned or mode == "build_fails"
    return runner.RUNS[run_id]


def test_healthy_project(tmp_path):
    result = run(tmp_path, "fast")
    assert result["status"] == "done" and result["runs_successfully"]
    assert result["stack"] == "flask"
    assert [e["path"] for e in result["endpoints"]] == ["/", "/books", "/about"]  # same site only
    assert [lvl["concurrent_users"] for lvl in result["load_test"]] == [1, 5, 10]
    assert all(lvl["error_rate"] == 0 for lvl in result["load_test"])
    # Timings vary with machine load; only latency findings may appear on a busy machine.
    assert {f["type"] for f in result["flags"]} <= {"slow_under_load"}
    assert result["overall_performance_score"] >= 80


def test_slow_project(tmp_path):
    result = run(tmp_path, "slow")
    assert result["load_test"][-1]["p95_ms"] >= 400
    assert result["flags"][0]["type"] == "slow_under_load"
    assert result["overall_performance_score"] in (80.0, 90.0)


def test_server_errors(tmp_path):
    result = run(tmp_path, "errors")
    assert result["load_test"][0]["error_rate"] == 1.0
    types = {f["type"] for f in result["flags"]}
    assert {"errors_under_load", "server_errors"} <= types
    assert result["overall_performance_score"] <= 45


def test_memory_growth(tmp_path):
    result = run(tmp_path, "leak")
    assert result["memory_leak_suspected"] and result["memory_peak_mb"] == 290.0  # idle + 3 levels
    assert any(f["type"] == "memory_growth" for f in result["flags"])


def test_crash_and_build_failure_score_zero(tmp_path):
    crashed = run(tmp_path, "crash")
    assert crashed["runs_successfully"] is False and crashed["overall_performance_score"] == 0.0
    assert "flask_sqlalchemy" in crashed["logs"]
    failed = run(tmp_path, "build_fails")
    assert failed["error"] == "Build failed" and "flaskk" in failed["logs"]


# ---- API -----------------------------------------------------------------------------


def token(role="service"):
    payload = {"sub": "svc", "role": role, "type": "access", "exp": time.time() + 60}
    return {"Authorization": "Bearer " + jwt.encode(payload, get_settings().jwt_secret, "HS256")}


def test_api_run_lifecycle(monkeypatch):
    monkeypatch.setattr(runs, "backend_factory", lambda: FakeBackend("fast"))
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content in FLASK.items():
            bundle.writestr(name, content)
    files = {"file": ("code.zip", buffer.getvalue())}
    assert client.post("/internal/runs", files=files, headers=token("admin")).status_code == 403
    started = client.post("/internal/runs", files=files, headers=token())
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    for _ in range(100):
        state = client.get(f"/internal/runs/{run_id}", headers=token()).json()
        if state["status"] == "done":
            break
        time.sleep(0.1)
    assert state["status"] == "done" and state["runs_successfully"]
    assert state["overall_performance_score"] >= 80
    assert client.get("/internal/runs/nope", headers=token()).status_code == 404


def test_api_without_docker(monkeypatch):
    def broken():
        raise RuntimeError("no socket")

    monkeypatch.setattr(runs, "backend_factory", broken)
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("app.py", "x")
    response = client.post("/internal/runs", files={"file": ("c.zip", buffer.getvalue())},
                           headers=token())  # fmt: skip
    assert response.status_code == 503


def test_score_rules():
    healthy = {"runs_successfully": True, "startup_seconds": 2,
               "load_test": [{"concurrent_users": 50, "p95_ms": 120, "error_rate": 0}],
               "endpoints": [{"status": 200}], "memory_peak_mb": 80}  # fmt: skip
    assert runner.score(healthy) == (100.0, [])
    slow = {**healthy, "startup_seconds": 25,
            "load_test": [{"concurrent_users": 50, "p95_ms": 1500, "error_rate": 0.1}],
            "unresponsive_under_load": True, "memory_peak_mb": 450}  # fmt: skip
    value, flags = runner.score(slow)
    # startup 10 + p95 20 + errors 10 + unresponsive 30 + memory 10
    assert value == 20.0
    assert {f["type"] for f in flags} == {"slow_startup", "slow_under_load", "errors_under_load",
                                          "unresponsive", "high_memory"}  # fmt: skip
