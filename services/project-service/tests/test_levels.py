import json

from tests.test_fingerprint import GENERATED
from tests.test_projects import submit


def make_course(client, users, **fields):
    body = {"name": "برمجة 1", "code": fields.pop("code", "CS101"), **fields}
    course = client.post("/api/v1/courses", json=body, headers=users["faculty"].headers).json()
    client.post(f"/api/v1/courses/{course['id']}/students", headers=users["faculty"].headers,
                json={"student_ids": [str(users["student"].id)]})  # fmt: skip
    return course


def test_course_level_and_kind_set_the_default_weights(client, users):
    faculty = users["faculty"].headers
    assignment = make_course(client, users, level="year1", kind="assignment")
    assert (assignment["level"], assignment["kind"]) == ("year1", "assignment")
    weights = {c["criterion"]: c for c in
               client.get(f"/api/v1/courses/{assignment['id']}/criteria", headers=faculty).json()}  # fmt: skip
    assert weights["report"]["weight"] == 0 and weights["code_quality"]["weight"] == 45
    assert all(c["is_default"] for c in weights.values())
    assert sum(c["weight"] for c in weights.values()) == 100

    graduation = make_course(client, users, code="CS499")  # old clients: unchanged behaviour
    assert (graduation["level"], graduation["kind"]) == ("year4", "graduation")
    bad = client.post("/api/v1/courses", json={"name": "x", "code": "X1", "level": "year9"},
                      headers=faculty)  # fmt: skip
    assert bad.status_code == 422


def test_an_assignment_is_not_penalized_for_having_no_report(client, users):
    course = make_course(client, users, level="year1", kind="assignment")
    pid = submit(client, users["student"], course["id"]).json()["id"]  # code only
    grade = client.get(f"/api/v1/grades/{pid}", headers=users["faculty"].headers).json()
    # Code, security and authenticity are known: 70 of the 100 points; only the viva is missing.
    assert grade["coverage"] == 70.0
    assert grade["missing_criteria"] == ["viva"]


def test_viva_and_fingerprint_follow_the_level(client, users, analyzer):
    course = make_course(client, users, level="year1", kind="assignment")
    pid = submit(client, users["student"], course["id"]).json()["id"]
    analyzer.routes["/internal/sessions"] = (
        201,
        {"session_id": "00000000-0000-0000-0000-000000000001"},
    )
    client.post(f"/api/v1/viva/start/{pid}", headers=users["student"].headers)
    sent = next(r for r in analyzer.route_calls if r.url.path == "/internal/sessions")
    assert json.loads(sent.content)["context"]["profile"] == {
        "level": "year1",
        "kind": "assignment",
    }

    analyzer.routes["/api/v1/challenge/mutations"] = (
        200,
        {"challenges": GENERATED["challenges"][:2]},
    )
    state = client.post(f"/api/v1/fingerprint/{pid}/start", headers=users["student"].headers).json()
    asked = next(r for r in analyzer.route_calls if r.url.path == "/api/v1/challenge/mutations")
    body = asked.content.decode("utf-8", errors="replace")
    assert 'name="count"\r\n\r\n2' in body and 'name="min_lines"\r\n\r\n4' in body
    assert all(c["seconds_allowed"] == 360 for c in state["challenges"])
