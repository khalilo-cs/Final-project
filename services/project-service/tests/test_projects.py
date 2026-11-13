import io
import zipfile

import pytest


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("main.py", "print('hi')\n")
    return buffer.getvalue()


PDF = b"%PDF-1.4\n%fake report\n"


@pytest.fixture
def course(client, users):
    response = client.post(
        "/api/v1/courses",
        json={"name": "مشروع التخرج", "code": "CS499", "semester": "Fall", "year": 2026},
        headers=users["faculty"].headers,
    )
    assert response.status_code == 201
    course = response.json()
    enrolled = client.post(
        f"/api/v1/courses/{course['id']}/students",
        json={"student_ids": [str(users["student"].id)]},
        headers=users["faculty"].headers,
    )
    assert enrolled.status_code == 200
    return course


def submit(client, user, course_id, code=None, report=None, **fields):
    files = {"code": ("code.zip", code if code is not None else make_zip(), "application/zip")}
    if report is not None:
        files["report"] = report
    data = {"title": "نظام إدارة مكتبة", "course_id": course_id, **fields}
    return client.post("/api/v1/projects", data=data, files=files, headers=user.headers)


# ---- courses -------------------------------------------------------------------------


def test_course_creation_rules(client, users):
    body = {"name": "X", "code": "CS1"}
    assert client.post("/api/v1/courses", json=body).status_code == 401
    assert (
        client.post("/api/v1/courses", json=body, headers=users["student"].headers).status_code
        == 403
    )
    # Faculty cannot create a course for someone else.
    other = {**body, "faculty_id": str(users["other_faculty"].id)}
    assert (
        client.post("/api/v1/courses", json=other, headers=users["faculty"].headers).status_code
        == 403
    )
    # Admin must say which faculty member owns it.
    assert (
        client.post("/api/v1/courses", json=body, headers=users["admin"].headers).status_code == 422
    )
    created = client.post("/api/v1/courses", json=other, headers=users["admin"].headers)
    assert created.status_code == 201
    assert created.json()["faculty_id"] == str(users["other_faculty"].id)
    assert (
        client.post("/api/v1/courses", json=other, headers=users["admin"].headers).status_code
        == 409
    )


def test_course_visibility(client, users, course):
    def codes(user):
        return [c["code"] for c in client.get("/api/v1/courses", headers=user.headers).json()]

    assert codes(users["faculty"]) == ["CS499"]
    assert codes(users["other_faculty"]) == []
    assert codes(users["student"]) == ["CS499"]
    assert codes(users["other_student"]) == []
    assert codes(users["admin"]) == ["CS499"]

    url = f"/api/v1/courses/{course['id']}"
    assert client.get(url, headers=users["student"].headers).status_code == 200
    assert client.get(url, headers=users["other_student"].headers).status_code == 403
    assert client.get(url, headers=users["other_faculty"].headers).status_code == 403


def test_enrollment_management(client, users, course):
    url = f"/api/v1/courses/{course['id']}/students"
    second = str(users["other_student"].id)
    assert (
        client.post(
            url, json={"student_ids": [second]}, headers=users["student"].headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json={"student_ids": [second]}, headers=users["other_faculty"].headers
        ).status_code
        == 403
    )
    # Idempotent, duplicates ignored.
    response = client.post(
        url, json={"student_ids": [second, second]}, headers=users["faculty"].headers
    )
    assert sorted(response.json()) == sorted([str(users["student"].id), second])
    assert len(client.get(url, headers=users["faculty"].headers).json()) == 2
    assert client.get(url, headers=users["student"].headers).status_code == 403

    assert client.delete(f"{url}/{second}", headers=users["faculty"].headers).status_code == 204
    assert client.get(url, headers=users["faculty"].headers).json() == [str(users["student"].id)]


# ---- submission + analysis -----------------------------------------------------------


def test_submit_runs_analysis_and_stores_results(client, users, course, analyzer):
    response = submit(
        client,
        users["student"],
        course["id"],
        report=("report.pdf", PDF, "application/pdf"),
        frameworks='["FastAPI", "React"]',
        git_url="https://github.com/student/library",
    )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["has_report"] is True
    assert project["frameworks"] == ["FastAPI", "React"]
    assert project["student_id"] == str(users["student"].id)

    # The background task ran after the response: analyzer called with a service token.
    assert len(analyzer.calls) == 1
    assert analyzer.calls[0].headers["authorization"].startswith("Bearer ")

    pid = project["id"]
    status = client.get(f"/api/v1/projects/{pid}/status", headers=users["student"].headers).json()
    assert status["status"] == "analyzed" and status["analysis_error"] is None
    detail = client.get(f"/api/v1/projects/{pid}", headers=users["student"].headers).json()
    assert detail["programming_languages"] == ["python"]  # detected, none declared

    code = client.get(f"/api/v1/analysis/code/{pid}/results", headers=users["faculty"].headers)
    assert code.status_code == 200 and code.json()["overall_quality_score"] == 95.0
    security = client.get(
        f"/api/v1/analysis/security/{pid}/results", headers=users["student"].headers
    )
    assert security.json()["critical_count"] == 1


def test_submit_requires_enrolled_student(client, users, course):
    assert submit(client, users["other_student"], course["id"]).status_code == 403
    assert submit(client, users["faculty"], course["id"]).status_code == 403
    missing = "00000000-0000-0000-0000-000000000001"
    assert submit(client, users["student"], missing).status_code == 404


def test_submit_validates_files(client, users, course, analyzer):
    student = users["student"]
    assert submit(client, student, course["id"], code=b"not a zip").status_code == 400
    exe = ("report.exe", b"MZ...", "application/octet-stream")
    assert submit(client, student, course["id"], report=exe).status_code == 400
    fake_pdf = ("report.pdf", b"<html>", "application/pdf")
    assert submit(client, student, course["id"], report=fake_pdf).status_code == 400
    assert submit(client, student, course["id"], git_url="javascript:alert(1)").status_code == 422
    assert submit(client, student, course["id"], frameworks="[1, 2]").status_code == 422
    assert analyzer.calls == []
    # Nothing half-saved.
    assert client.get("/api/v1/projects", headers=student.headers).json() == []


def test_upload_size_limit(client, users, course, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_code_mb", 0)
    assert submit(client, users["student"], course["id"]).status_code == 413


def test_analyzer_failures_are_recorded(client, users, course, analyzer):
    analyzer.status = 503
    pid = submit(client, users["student"], course["id"]).json()["id"]
    status = client.get(f"/api/v1/projects/{pid}/status", headers=users["student"].headers).json()
    assert status["status"] == "analysis_failed"
    assert "unavailable" in status["analysis_error"]
    results = client.get(f"/api/v1/analysis/code/{pid}/results", headers=users["student"].headers)
    assert results.status_code == 404

    # Staff can re-run once the analyzer is back; students cannot.
    analyzer.status = 200
    rerun = f"/api/v1/analysis/code/{pid}"
    assert client.post(rerun, headers=users["student"].headers).status_code == 403
    assert client.post(rerun, headers=users["faculty"].headers).status_code == 202
    status = client.get(f"/api/v1/projects/{pid}/status", headers=users["faculty"].headers).json()
    assert status["status"] == "analyzed"


def test_rejected_archive(client, users, course, analyzer):
    analyzer.status = 400
    analyzer.body = {"detail": "unsafe path in archive: ../x"}
    pid = submit(client, users["student"], course["id"]).json()["id"]
    status = client.get(f"/api/v1/projects/{pid}/status", headers=users["student"].headers).json()
    assert status["status"] == "analysis_failed"
    assert status["analysis_error"] == "Code archive rejected: unsafe path in archive: ../x"


def test_project_visibility(client, users, course):
    pid = submit(client, users["student"], course["id"]).json()["id"]
    url = f"/api/v1/projects/{pid}"
    for allowed in ("student", "faculty", "admin"):
        assert client.get(url, headers=users[allowed].headers).status_code == 200
    for denied in ("other_student", "other_faculty"):
        assert client.get(url, headers=users[denied].headers).status_code == 404
        results = f"/api/v1/analysis/code/{pid}/results"
        assert client.get(results, headers=users[denied].headers).status_code == 404

    listing = f"/api/v1/courses/{course['id']}/projects"
    assert len(client.get(listing, headers=users["faculty"].headers).json()) == 1
    assert len(client.get(listing, headers=users["student"].headers).json()) == 1
    assert client.get(listing, headers=users["other_student"].headers).status_code == 403


def test_delete_project(client, users, course):
    from app.services.storage import project_dir

    pid = submit(client, users["student"], course["id"]).json()["id"]
    assert project_dir(pid).exists()
    url = f"/api/v1/projects/{pid}"
    assert client.delete(url, headers=users["other_student"].headers).status_code == 404
    assert client.delete(url, headers=users["student"].headers).status_code == 204
    assert client.get(url, headers=users["student"].headers).status_code == 404
    assert not project_dir(pid).exists()


def test_rejects_bad_tokens(client, users):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/projects", headers={"Authorization": "Bearer x"}).status_code == 401
