import base64
import io
import json
import zipfile

import pytest

from tests.test_grading import REPORT, course, project  # noqa: F401  (fixtures)
from tests.test_projects import SQL, submit

FIXES = [
    {"id": "abc123", "file": "app.py", "line": 3, "type": "SQL Injection", "kind": "patch",
     "title": "Use a parameterized query", "explanation": "...", "diff": "--- a/app.py",
     "example": None},
    {"id": "def456", "file": "D.java", "line": 1, "type": "SQL Injection", "kind": "suggestion",
     "title": "Use PreparedStatement", "explanation": "...", "diff": None, "example": "ps"},
]  # fmt: skip


def fixed_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("main.py", "print('fixed')\n")
    return buffer.getvalue()


@pytest.fixture
def ai(analyzer):
    analyzer.routes.update(
        {
            "/api/v1/fixes/propose": (200, FIXES),
            "/api/v1/fixes/apply": (
                200,
                {
                    "applied": [
                        {
                            "id": "abc123",
                            "file": "app.py",
                            "line": 3,
                            "type": "SQL Injection",
                            "title": "Use a parameterized query",
                        }
                    ],
                    "skipped": [{"id": "def456", "reason": "advice only, change it by hand"}],
                    "archive_base64": base64.b64encode(fixed_zip()).decode(),
                },
            ),  # fmt: skip
            "/internal/advice/summary": (200, {"summary": "ملخص", "written_by": "claude"}),
        }
    )
    return analyzer


def test_advice_has_strengths_weaknesses_improvements_and_fixes(client, users, project, ai):
    advice = client.get(f"/api/v1/projects/{project}/advice", headers=users["student"].headers)
    assert advice.status_code == 200
    body = advice.json()
    weaknesses = " ".join(w["title"] for w in body["weaknesses"])
    assert "SQL Injection" in weaknesses and "42.0%" in weaknesses
    assert "لا توجد اختبارات آلية" in weaknesses
    assert body["improvements"][0]["priority"] == "high"
    assert any("parameterized" in i["title"] for i in body["improvements"])
    assert [f["id"] for f in body["fixes"]] == ["abc123", "def456"]
    assert body["summary"] == {"summary": "ملخص", "written_by": "claude"}
    hidden = client.get(
        f"/api/v1/projects/{project}/advice", headers=users["other_student"].headers
    )
    assert hidden.status_code == 404


def test_advice_survives_ai_services_being_down(client, users, project, analyzer):
    analyzer.routes["/api/v1/fixes/propose"] = (503, {})
    analyzer.routes["/internal/advice/summary"] = (503, {})
    body = client.get(f"/api/v1/projects/{project}/advice", headers=users["faculty"].headers).json()
    assert body["fixes"] is None and body["summary"] is None and body["weaknesses"]


def test_fixes_need_the_students_approval(client, users, project, ai):
    url = f"/api/v1/projects/{project}/fixes/apply"
    body = {"fix_ids": ["abc123", "def456"]}
    assert client.post(url, json=body, headers=users["faculty"].headers).status_code == 403
    response = client.post(url, json=body, headers=users["student"].headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert [a["id"] for a in result["applied"]] == ["abc123"]
    assert result["skipped"][0]["reason"] == "advice only, change it by hand"
    sent = json.loads(_field(ai.route_calls[-1], "fix_ids"))
    assert sent == ["abc123", "def456"]

    student = users["student"].headers
    current = client.get(f"/api/v1/projects/{project}/code", headers=student)
    assert zipfile.ZipFile(io.BytesIO(current.content)).read("main.py") == b"print('fixed')\n"
    original = client.get(f"/api/v1/projects/{project}/code?original=true", headers=student)
    assert b"def main" in zipfile.ZipFile(io.BytesIO(original.content)).read("main.py")

    # Faculty see what the AI changed, as an alert and in the advice.
    alerts = client.get("/api/v1/dashboard/faculty/alerts", headers=users["faculty"].headers).json()
    assert any(a["type"] == "ai_fixes_applied" for a in alerts)
    advice = client.get(
        f"/api/v1/projects/{project}/advice", headers=users["faculty"].headers
    ).json()
    assert advice["applied_fixes"][0]["fix_id"] == "abc123"

    client.put(f"/api/v1/grades/{project}", json={"total": 80}, headers=users["faculty"].headers)
    assert client.post(url, json=body, headers=student).status_code == 409  # graded: frozen


def _field(request, name):
    marker = f'name="{name}"\r\n\r\n'.encode()
    content = request.content
    start = content.index(marker) + len(marker)
    return content[start : content.index(b"\r\n--", start)].decode()


def test_viva_start_context_and_score_in_grade(client, users, project, analyzer):
    session_id = "11111111-1111-1111-1111-111111111111"
    analyzer.routes["/internal/sessions"] = (
        201, lambda request: {"session_id": session_id, "status": "in_progress",
                              "current_question": {"text": "q"}},
    )  # fmt: skip
    analyzer.routes["/internal/sessions/*"] = (
        200,
        {"status": "in_progress", "overall_score": None},
    )

    url = f"/api/v1/viva/start/{project}"
    assert client.post(url, headers=users["faculty"].headers).status_code == 403
    state = client.post(url, json={"language": "en"}, headers=users["student"].headers)
    assert state.status_code == 201 and state.json()["session_id"] == session_id
    sent = json.loads(analyzer.route_calls[-1].content)
    assert sent["language"] == "en"
    assert sent["staff_ids"] == [str(users["faculty"].id)]
    assert sent["context"]["title"] == "نظام إدارة مكتبة"
    assert sent["context"]["vulnerabilities"][0]["type"] == "SQL Injection"
    assert sent["context"]["technologies"] == ["Flask"]
    assert sent["context"]["database"]["normalization_level"] == "2NF"
    (function,) = sent["context"]["functions"]
    assert function["function"] == "main" and function["code"].startswith("def main():")

    faculty = users["faculty"].headers
    assert client.get(f"/api/v1/grades/{project}", headers=faculty).json()["coverage"] == 55.0

    analyzer.routes["/internal/sessions/*"] = (200, {"status": "completed", "overall_score": 70.0})
    grade = client.get(f"/api/v1/grades/{project}", headers=faculty).json()
    assert grade["coverage"] == 80.0 and grade["status"] == "viva_completed"
    viva = next(b for b in grade["breakdown"] if b["criterion"] == "viva")
    assert viva["score"] == 70.0 and "viva score" in viva["justification"]
    # code 95x20 + security 75x10 + db 80x10 + report 61.5x15 + viva 70x25 -> 6122.5 / 80
    assert grade["suggested_total"] == 76.5
    sessions = client.get(f"/api/v1/viva/project/{project}", headers=faculty).json()
    assert sessions[0]["score"] == 70.0


def test_viva_requires_analysis(client, users, course, analyzer):  # noqa: F811
    analyzer.status = 503
    pid = submit(client, users["student"], course["id"], report=REPORT, database=SQL).json()["id"]
    response = client.post(f"/api/v1/viva/start/{pid}", headers=users["student"].headers)
    assert response.status_code == 409
