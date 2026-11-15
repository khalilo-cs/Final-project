import io

import pytest
from openpyxl import load_workbook

from tests.test_projects import PDF, SQL, submit

REPORT = ("report.pdf", PDF, "application/pdf")


@pytest.fixture
def course(client, users):
    course = client.post(
        "/api/v1/courses",
        json={"name": "مشروع التخرج", "code": "CS499"},
        headers=users["faculty"].headers,
    ).json()
    client.post(
        f"/api/v1/courses/{course['id']}/students",
        json={"student_ids": [str(users["student"].id)]},
        headers=users["faculty"].headers,
    )
    return course


@pytest.fixture
def project(client, users, course):
    response = submit(client, users["student"], course["id"], report=REPORT, database=SQL)
    return response.json()["id"]


def test_suggested_grade_and_justification(client, users, project):
    grade = client.get(f"/api/v1/grades/{project}", headers=users["faculty"].headers).json()
    # authenticity: similarity 100 x30, style 100 x15, report (100-42) x10 -> 5080 / 55 = 92.4
    # code 95 x20, security 75 x10, database 80 x10, report 61.5 x15, authenticity 92.4 x10
    # -> 5296.5 / 65
    assert grade["suggested_total"] == 81.5
    assert grade["coverage"] == 65.0
    assert grade["missing_criteria"] == ["viva", "performance"]
    rows = {row["criterion"]: row for row in grade["breakdown"]}
    assert rows["code_quality"]["points"] == 19.0
    assert rows["security"]["justification"].startswith("1 critical")
    assert "SQL Injection" in rows["security"]["justification"]
    assert "plagiarism 42.0%" in rows["report"]["justification"]
    assert rows["viva"]["score"] is None and rows["viva"]["label_ar"] == "المناقشة"
    assert {a["type"] for a in grade["alerts"]} == {
        "plagiarism",
        "critical_vulnerability",
        "report_inconsistency",
        "database_design",
    }
    assert grade["final_total"] is None


def test_students_only_see_the_final_grade(client, users, project):
    student = users["student"].headers
    before = client.get(f"/api/v1/grades/{project}", headers=student).json()
    assert before == {
        "project_id": project,
        "status": "analyzed",
        "final_total": None,
        "graded_at": None,
    }
    client.put(f"/api/v1/grades/{project}", json={"total": 85}, headers=users["faculty"].headers)
    after = client.get(f"/api/v1/grades/{project}", headers=student).json()
    assert after["final_total"] == 85 and after["status"] == "graded"
    assert "suggested_total" not in after


def test_faculty_sets_grade_and_it_is_logged(client, users, project):
    from sqlalchemy import select

    from app import database
    from app.models.grading import LearningLog

    url = f"/api/v1/grades/{project}"
    body = {"total": 85, "notes": "المناقشة كانت ممتازة"}
    assert client.put(url, json=body, headers=users["student"].headers).status_code == 403
    assert client.put(url, json=body, headers=users["other_faculty"].headers).status_code == 404
    assert client.put(url, json={"total": 101}, headers=users["faculty"].headers).status_code == 422
    graded = client.put(url, json=body, headers=users["faculty"].headers).json()
    assert graded["final_total"] == 85 and graded["status"] == "graded"
    assert graded["faculty_notes"] == "المناقشة كانت ممتازة"
    client.put(url, json={"total": 88}, headers=users["faculty"].headers)

    with database.SessionLocal() as db:
        logs = db.scalars(select(LearningLog).order_by(LearningLog.created_at)).all()
    assert [log.adjusted_value["total"] for log in logs] == [85, 88]
    assert logs[0].original_value["suggested_total"] == 81.5
    assert logs[1].original_value["previous_final"] == 85


def test_course_weights(client, users, course, project):
    url = f"/api/v1/courses/{course['id']}/criteria"
    faculty = users["faculty"].headers
    defaults = client.get(url, headers=users["student"].headers).json()
    assert sum(c["weight"] for c in defaults) == 100 and all(c["is_default"] for c in defaults)

    assert client.put(url, json={"weights": {"viva": 5}}, headers=faculty).status_code == 422
    assert client.put(url, json={"weights": {"luck": 0}}, headers=faculty).status_code == 422
    change = {"weights": {"viva": 15, "code_quality": 30}}
    assert client.put(url, json=change, headers=users["student"].headers).status_code == 403
    updated = {c["criterion"]: c for c in client.put(url, json=change, headers=faculty).json()}
    assert updated["code_quality"]["weight"] == 30 and not updated["code_quality"]["is_default"]

    grade = client.get(f"/api/v1/grades/{project}", headers=faculty).json()
    # code 95 x30, security 75 x10, database 80 x10, report 61.5 x15, authenticity 92.4 x10
    # -> 6246.5 / 75
    assert grade["suggested_total"] == 83.3


def test_course_grades_and_excel(client, users, course, analyzer):
    student_id = str(users["student"].id)
    analyzer.users = {
        student_id: {
            "id": student_id,
            "username": "sara",
            "full_name": "سارة علي",
            "student_id": "2022123",
        }
    }
    submit(client, users["student"], course["id"], title='=HYPERLINK("http://evil")')
    faculty = users["faculty"].headers

    listing = client.get(f"/api/v1/grades/course/{course['id']}", headers=faculty).json()
    (row,) = listing["projects"]
    assert row["student_name"] == "سارة علي" and row["student_number"] == "2022123"
    assert (
        client.get(
            f"/api/v1/grades/course/{course['id']}", headers=users["student"].headers
        ).status_code
        == 403
    )

    response = client.get(f"/api/v1/reports/course/{course['id']}/excel", headers=faculty)
    assert response.status_code == 200
    assert "grades-CS499.xlsx" in response.headers["content-disposition"]
    sheet = load_workbook(io.BytesIO(response.content)).active
    assert sheet.sheet_view.rightToLeft is True
    assert sheet["A1"].value == "كشف درجات: CS499 - مشروع التخرج"
    assert sheet["A2"].value == "الرقم الجامعي" and sheet["E2"].value == "جودة الكود (20%)"
    assert [sheet.cell(3, c).value for c in (1, 2)] == ["2022123", "سارة علي"]
    assert sheet["C3"].value == '\'=HYPERLINK("http://evil")'  # not a live formula


def test_names_missing_when_auth_is_down(client, users, course, analyzer):
    analyzer.auth_up = False
    submit(client, users["student"], course["id"])
    listing = client.get(
        f"/api/v1/grades/course/{course['id']}", headers=users["faculty"].headers
    ).json()
    assert listing["projects"][0]["student_name"] is None


def test_dashboard(client, users, project):
    faculty = users["faculty"].headers
    summary = client.get("/api/v1/dashboard/faculty/summary", headers=faculty).json()
    assert summary["total_projects"] == 1
    assert summary["by_status"] == {"analyzed": 1}
    assert summary["average_suggested_total"] == 81.5
    assert summary["average_by_criterion"]["security"] == 75.0
    assert summary["average_by_criterion"]["viva"] is None

    alerts = client.get("/api/v1/dashboard/faculty/alerts", headers=faculty).json()
    assert [a["severity"] for a in alerts] == ["High", "High", "Medium", "Low"]
    assert alerts[0]["project_id"] == project

    other = users["other_faculty"].headers
    assert client.get("/api/v1/dashboard/faculty/alerts", headers=other).json() == []
    assert (
        client.get(
            "/api/v1/dashboard/faculty/summary", headers=users["student"].headers
        ).status_code
        == 403
    )


def test_department_analytics(client, users, project):
    faculty = users["faculty"].headers
    data = client.get("/api/v1/dashboard/department/analytics", headers=faculty).json()
    assert data["projects"] == 1 and data["graded"] == 0
    assert {"name": "أمان: SQL Injection", "count": 1} in data["common_issues"]
    assert data["languages"] == [{"name": "Python", "count": 1}]
    assert data["technologies"] == [{"name": "Flask", "count": 1}]
    assert sum(b["count"] for b in data["grade_distribution"]) == 1
    assert next(b for b in data["grade_distribution"] if b["count"])["range"] == "80-89"
    assert data["terms"] == [{"term": "CS499", "projects": 1, "average": 81.5}]
    assert client.get("/api/v1/dashboard/department/analytics",
                      headers=users["student"].headers).status_code == 403  # fmt: skip
