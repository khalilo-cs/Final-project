import copy

from app.services import notify
from tests.conftest import ANALYZER_RESPONSE
from tests.test_grading import REPORT, course  # noqa: F401  (fixture)
from tests.test_projects import SQL, submit


def inbox(client, user, **params):
    response = client.get("/api/v1/notifications", headers=user.headers, params=params)
    assert response.status_code == 200
    return response.json()


def test_submission_analysis_and_grade_notify_the_right_people(client, users, course):  # noqa: F811
    project = submit(client, users["student"], course["id"], report=REPORT, database=SQL).json()

    faculty = inbox(client, users["faculty"])
    kinds = [n["kind"] for n in faculty["items"]]
    assert "new_submission" in kinds
    new = next(n for n in faculty["items"] if n["kind"] == "new_submission")
    assert new["link"] == f"/projects/{project['id']}" and not new["read"]

    student = inbox(client, users["student"])
    assert [n["kind"] for n in student["items"]] == ["analysis_done"]
    assert student["unread"] == 1

    graded = client.put(
        f"/api/v1/grades/{project['id']}",
        json={"total": 88.5, "notes": "عمل جيد"},
        headers=users["faculty"].headers,
    )
    assert graded.status_code == 200
    latest = inbox(client, users["student"])["items"][0]
    assert latest["kind"] == "grade_final" and "88.5" in latest["body"]

    # Nobody else sees them.
    assert inbox(client, users["other_student"])["items"] == []
    assert inbox(client, users["other_faculty"])["items"] == []


def test_serious_alerts_reach_the_faculty(client, users, course, analyzer):  # noqa: F811
    response = copy.deepcopy(ANALYZER_RESPONSE)
    response["security"]["vulnerabilities"] = [
        {"type": "SQL Injection", "severity": "Critical", "file": "a.py", "line": 3,
         "description": "x", "evidence": "x"}
    ]  # fmt: skip
    response["security"]["critical_count"], response["security"]["high_count"] = 1, 0
    analyzer.routes["/api/v1/analysis/code"] = (200, response)
    submit(client, users["student"], course["id"])
    alert = next(
        n for n in inbox(client, users["faculty"])["items"] if n["kind"] == "project_alert"
    )
    assert alert["body"] == "ثغرة أمنية حرجة واحدة"


def test_mark_read(client, users, course):  # noqa: F811
    submit(client, users["student"], course["id"])
    student = users["student"]
    (item,) = inbox(client, student)["items"]
    other = client.post(
        f"/api/v1/notifications/{item['id']}/read", headers=users["other_student"].headers
    )
    assert other.status_code == 404
    read = client.post(f"/api/v1/notifications/{item['id']}/read", headers=student.headers)
    assert read.json()["read"] is True
    assert inbox(client, student)["unread"] == 0
    assert inbox(client, student, unread_only=True)["items"] == []

    submit(client, student, course["id"])
    marked = client.post("/api/v1/notifications/read-all", headers=student.headers).json()
    assert marked == {"marked": 1}
    assert client.get("/api/v1/notifications").status_code == 401


def test_emails_only_when_smtp_is_configured(monkeypatch):
    started = []
    monkeypatch.setattr(notify.threading, "Thread", lambda **kw: started.append(kw) or _Noop())
    notify.send_emails([object()])
    assert started == []
    monkeypatch.setattr(notify.get_settings(), "smtp_host", "smtp.example.edu")
    notify.send_emails([_N()])
    assert len(started) == 1


class _Noop:
    def start(self):
        pass


class _N:
    user_id = "u"
    title = "t"
    body = "b"
    link = "/projects/1"


def test_arabic_counts():
    from app.services.arabic import count_phrase

    forms = ("ثغرة واحدة", "ثغرتان", "ثغرات", "ثغرة")
    assert [count_phrase(n, *forms) for n in (1, 2, 3, 10, 11, 100, 103)] == [
        "ثغرة واحدة", "ثغرتان", "3 ثغرات", "10 ثغرات", "11 ثغرة", "100 ثغرة", "103 ثغرات",
    ]  # fmt: skip
