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
    apply_call = next(r for r in ai.route_calls if r.url.path == "/api/v1/fixes/apply")
    sent = json.loads(_field(apply_call, "fix_ids"))
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
    assert client.get(f"/api/v1/grades/{project}", headers=faculty).json()["coverage"] == 65.0

    analyzer.routes["/internal/sessions/*"] = (200, {"status": "completed", "overall_score": 70.0})
    grade = client.get(f"/api/v1/grades/{project}", headers=faculty).json()
    assert grade["coverage"] == 90.0 and grade["status"] == "viva_completed"
    viva = next(b for b in grade["breakdown"] if b["criterion"] == "viva")
    assert viva["score"] == 70.0 and "viva score" in viva["justification"]
    # authenticity now includes the viva gap: code 95 - viva 70 = 25 -> 100 - 5 x 2.5 = 87.5
    # (100x30 + 100x15 + 87.5x25 + 58x10) / 80 = 90.8
    # code 95x20 + security 75x10 + db 80x10 + report 61.5x15 + viva 70x25 + auth 90.8x10
    # -> 7030.5 / 90
    assert grade["suggested_total"] == 78.1
    sessions = client.get(f"/api/v1/viva/project/{project}", headers=faculty).json()
    assert sessions[0]["score"] == 70.0


def test_viva_requires_analysis(client, users, course, analyzer):  # noqa: F811
    analyzer.status = 503
    pid = submit(client, users["student"], course["id"], report=REPORT, database=SQL).json()["id"]
    response = client.post(f"/api/v1/viva/start/{pid}", headers=users["student"].headers)
    assert response.status_code == 409


def test_every_analyzed_project_is_sent_to_the_learner(client, users, course, analyzer):  # noqa: F811
    pid = submit(client, users["student"], course["id"], report=REPORT, database=SQL).json()["id"]
    lessons = [r for r in analyzer.route_calls if r.url.path == "/internal/learn/project"]
    assert len(lessons) == 1
    body = json.loads(lessons[0].content)
    assert body["project_id"] == pid
    assert body["context"]["technologies"] == ["Flask"]
    assert body["context"]["vulnerabilities"][0]["type"] == "SQL Injection"


def test_learning_failure_never_breaks_analysis(client, users, course, analyzer):  # noqa: F811
    analyzer.routes["/internal/learn/project"] = (503, {})
    pid = submit(client, users["student"], course["id"]).json()["id"]
    status = client.get(f"/api/v1/projects/{pid}/status", headers=users["student"].headers).json()
    assert status["status"] == "analyzed"


def test_authenticity_flags_a_copied_project(client, users, course, analyzer):  # noqa: F811
    other = submit(client, users["student"], course["id"]).json()["id"]
    analyzer.routes["/api/v1/fraud/analyze"] = (200, {
        "similarity": {"max_similarity": 0.72, "fingerprint_count": 90, "ignored_boilerplate": 0,
                       "corpus_size": 4,
                       "sources": [{"document_id": other, "similarity": 0.72,
                                    "reverse_similarity": 0.8, "matched_files": [
                                        {"file": "src/a.py", "lines": [1, 40],
                                         "other_file": "lib/b.py", "other_lines": [3, 44],
                                         "fingerprints": 30}]}]},
        "git": {"available": True, "score": 60, "total_commits": 1,
                "flags": [{"type": "single_commit", "severity": "high",
                           "evidence": "The whole project was committed at once"}]},
        "style": {"style_consistency_score": 70.0, "outliers": [
            {"file": "src/a.py", "lines": 40, "differs": {"naming": {}, "indent": {}}}]},
    })  # fmt: skip
    pid = submit(client, users["student"], course["id"], title="مشروع منسوخ").json()["id"]
    faculty = users["faculty"].headers
    result = client.get(f"/api/v1/fraud/{pid}/results", headers=faculty).json()
    # similarity 0 x30 (72% >= 60%), git 60 x20, style 70 x15 -> 2250 / 65
    assert result["authenticity_score"] == 34.6
    assert result["similar_projects"][0]["title"] == "نظام إدارة مكتبة"
    assert result["similar_projects"][0]["matched_files"][0]["other_file"] == "lib/b.py"
    assert {f["type"] for f in result["flags"]} == {"code_similarity", "git_single_commit",
                                                    "style_outlier"}  # fmt: skip
    assert result["similar_projects"][0]["submitted"] == "earlier"
    alerts = client.get("/api/v1/dashboard/faculty/alerts", headers=faculty).json()
    assert any(a["type"] == "authenticity" and a["severity"] == "High" and a["project_id"] == pid
               for a in alerts)  # fmt: skip
    # Students never see suspicion of copying.
    student = client.get(f"/api/v1/fraud/{pid}/results", headers=users["student"].headers)
    assert student.status_code == 403
    sent = [r for r in analyzer.route_calls if r.url.path == "/api/v1/fraud/analyze"][-1]
    assert other in _field(sent, "exclude_ids")  # own earlier project is not a "copy"


def test_the_original_author_is_not_treated_as_the_copier(client, users, course, analyzer):  # noqa: F811
    original = submit(client, users["student"], course["id"]).json()["id"]
    copy = submit(client, users["student"], course["id"], title="نسخة").json()["id"]
    # Re-analysing the original now finds the later copy.
    analyzer.routes["/api/v1/fraud/analyze"] = (200, {
        "similarity": {"max_similarity": 0.98, "fingerprint_count": 90, "ignored_boilerplate": 0,
                       "corpus_size": 2, "sources": [{"document_id": copy, "similarity": 0.98,
                                                      "reverse_similarity": 0.98,
                                                      "matched_files": []}]},
        "git": None, "style": {"style_consistency_score": 100.0, "outliers": []},
    })  # fmt: skip
    faculty = users["faculty"].headers
    client.post(f"/api/v1/analysis/code/{original}", headers=faculty)
    result = client.get(f"/api/v1/fraud/{original}/results", headers=faculty).json()
    similarity = next(c for c in result["components"] if c["factor"] == "code_similarity")
    assert similarity["score"] == 51.0  # 100 - 0.98 x 50: shared, not copied
    assert [f["type"] for f in result["flags"]] == ["code_shared"]
    assert result["similar_projects"][0]["submitted"] == "later"


def test_alerts_and_evidence_have_arabic_text(client, users, project, analyzer):  # noqa: F811
    alerts = client.get("/api/v1/dashboard/faculty/alerts", headers=users["faculty"].headers).json()
    assert alerts and all(a["message_ar"] for a in alerts)
    plagiarism = next(a for a in alerts if a["type"] == "plagiarism")
    assert plagiarism["message_ar"] == "42.0% من التقرير يطابق تقارير أخرى"


def test_duplicate_and_dead_code_advice(client, users, course, analyzer):  # noqa: F811
    import copy

    body = copy.deepcopy(analyzer.body)
    body["code"]["code_smells"] = [
        {"type": "duplicate_code", "file": "b.py", "line": 3, "symbol": "a.py:3-20", "message": "."},
        {"type": "dead_code", "file": "a.py", "line": 40, "symbol": "old_report", "message": "."},
    ]  # fmt: skip
    body["code"]["code_duplication_percentage"] = 22.5
    body["code"]["dead_code"] = [{"file": "a.py", "line": 40, "name": "old_report", "lines": 6}]
    analyzer.body = body
    pid = submit(client, users["student"], course["id"]).json()["id"]
    advice = client.get(f"/api/v1/projects/{pid}/advice", headers=users["student"].headers).json()
    titles = [i["title"] for i in advice["improvements"]]
    assert any("الكود المكرر" in t for t in titles)
    assert any("غير المستخدمة" in t for t in titles)
    assert not any("الدوال الطويلة" in t for t in titles)  # no length/complexity findings here
    weaknesses = [w["title"] for w in advice["weaknesses"]]
    assert "كود مكرر (نسخ ولصق) (1)" in weaknesses
