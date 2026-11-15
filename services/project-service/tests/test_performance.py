from tests.test_grading import REPORT, course, project  # noqa: F401  (fixtures)
from tests.test_projects import SQL, submit

DONE = {
    "run_id": "run1", "status": "done", "runs_successfully": True, "startup_seconds": 2.1,
    "overall_performance_score": 90.0, "memory_peak_mb": 120.0,
    "load_test": [{"concurrent_users": 50, "p95_ms": 420.0, "error_rate": 0.0}],
    "flags": [{"type": "slow_under_load", "severity": "Low",
               "evidence": "p95 420.0 ms with 50 users"}],
}  # fmt: skip


def test_performance_completes_the_grade(client, users, project, analyzer):  # noqa: F811
    faculty, student = users["faculty"].headers, users["student"].headers
    running = client.get(f"/api/v1/sandbox/{project}/results", headers=student).json()
    assert running["status"] == "running"
    grade = client.get(f"/api/v1/grades/{project}", headers=faculty).json()
    perf = next(b for b in grade["breakdown"] if b["criterion"] == "performance")
    assert perf["score"] is None and grade["coverage"] == 65.0

    analyzer.routes["/internal/runs/*"] = (200, DONE)
    grade = client.get(f"/api/v1/grades/{project}", headers=faculty).json()
    perf = next(b for b in grade["breakdown"] if b["criterion"] == "performance")
    assert perf["score"] == 90.0 and "p95 420.0 ms with 50 users" in perf["justification"]
    assert grade["coverage"] == 75.0  # viva still missing in this test
    # code 95x20 + security 75x10 + db 80x10 + report 61.5x15 + auth 92.4x10 + perf 90x10
    assert grade["suggested_total"] == 82.6
    advice = client.get(f"/api/v1/projects/{project}/advice", headers=student).json()
    assert any(w["category"] == "performance" for w in advice["weaknesses"])


def test_project_that_does_not_run(client, users, project, analyzer):  # noqa: F811
    analyzer.routes["/internal/runs/*"] = (200, {
        "run_id": "run1", "status": "done", "runs_successfully": False,
        "overall_performance_score": 0.0, "error": "The project did not answer HTTP requests",
        "flags": [{"type": "does_not_run", "severity": "High", "evidence": "..."}],
    })  # fmt: skip
    alerts = client.get("/api/v1/dashboard/faculty/alerts", headers=users["faculty"].headers).json()
    assert any(a["type"] == "does_not_run" and a["severity"] == "High" for a in alerts)
    advice = client.get(
        f"/api/v1/projects/{project}/advice", headers=users["student"].headers
    ).json()
    assert advice["improvements"][0]["category"] == "performance"


def test_without_docker_the_analysis_still_succeeds(client, users, course, analyzer):  # noqa: F811
    analyzer.routes["/internal/runs"] = (503, {"detail": "Docker is not available"})
    pid = submit(client, users["student"], course["id"], report=REPORT, database=SQL).json()["id"]
    student = users["student"].headers
    assert (
        client.get(f"/api/v1/projects/{pid}/status", headers=student).json()["status"] == "analyzed"
    )
    perf = client.get(f"/api/v1/sandbox/{pid}/results", headers=student).json()
    assert perf["status"] == "unavailable" and "Docker" in perf["error"]

    analyzer.routes["/internal/runs"] = (202, {"run_id": "run2", "status": "queued"})
    assert (
        client.post(
            f"/api/v1/sandbox/run/{pid}", headers=users["other_student"].headers
        ).status_code
        == 404
    )
    rerun = client.post(f"/api/v1/sandbox/run/{pid}", headers=student)
    assert rerun.status_code == 202 and rerun.json()["status"] == "running"


def test_lost_run_after_sandbox_restart(client, users, project, analyzer):  # noqa: F811
    analyzer.routes["/internal/runs/*"] = (404, {"detail": "Unknown run"})
    perf = client.get(f"/api/v1/sandbox/{project}/results", headers=users["faculty"].headers).json()
    assert perf["status"] == "lost"
