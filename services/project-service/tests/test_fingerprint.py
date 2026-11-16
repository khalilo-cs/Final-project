from datetime import timedelta

from app import database
from app.models.fingerprint import ComprehensionChallenge
from app.services import fingerprint
from tests.test_grading import course  # noqa: F401  (fixture)
from tests.test_projects import submit


def challenge(n: int, line: int, original: str, mutated: str) -> dict:
    code = "\n".join(["def f(x):", "    total = 0", mutated, "    return total"])
    return {
        "file": f"app/m{n}.py", "function": f"f{n}", "language": "python", "start_line": 10,
        "code": code,
        "mutation": {"line": line, "original_line": original, "mutated_line": mutated,
                     "kind": "boundary", "description_ar": "حدّ المقارنة", "description": "x"},
    }  # fmt: skip


GENERATED = {"challenges": [
    challenge(1, 12, "    if x <= 0:", "    if x < 0:"),
    challenge(2, 12, "    total += x", "    total -= x"),
    challenge(3, 12, "    if a and b:", "    if a or b:"),
]}  # fmt: skip
URL = "/api/v1/fingerprint"


def start(client, users, course, analyzer):  # noqa: F811
    analyzer.routes["/api/v1/challenge/mutations"] = (200, GENERATED)
    pid = submit(client, users["student"], course["id"]).json()["id"]
    response = client.post(f"{URL}/{pid}/start", headers=users["student"].headers)
    assert response.status_code == 201, response.text
    return pid, response.json()


def test_answers_are_hidden_until_the_student_has_answered(client, users, course, analyzer):  # noqa: F811
    pid, state = start(client, users, course, analyzer)
    student = users["student"].headers
    assert [c["status"] for c in state["challenges"]] == ["pending"] * 3
    assert all("answer" not in c and "code" not in c for c in state["challenges"])

    opened = client.post(f"{URL}/{pid}/next", headers=student).json()["challenges"][0]
    assert opened["status"] == "active" and "if x < 0:" in opened["code"]
    assert "answer" not in opened and 230 <= opened["seconds_left"] <= 240
    # Opening again does not skip ahead or restart the clock.
    again = client.post(f"{URL}/{pid}/next", headers=student).json()["challenges"]
    assert [c["status"] for c in again] == ["active", "pending", "pending"]

    # The professor sees everything; other students nothing.
    staff = client.get(f"{URL}/{pid}", headers=users["faculty"].headers).json()
    assert staff["challenges"][0]["answer"]["original_line"] == "    if x <= 0:"
    assert client.get(f"{URL}/{pid}", headers=users["other_student"].headers).status_code == 404
    forbidden = client.post(f"{URL}/{pid}/next", headers=users["faculty"].headers)
    assert forbidden.status_code == 403


def test_scoring_and_authenticity(client, users, course, analyzer):  # noqa: F811
    pid, _ = start(client, users, course, analyzer)
    student = users["student"].headers

    def play(line, fixed_line):
        state = client.post(f"{URL}/{pid}/next", headers=student).json()
        active = next(c for c in state["challenges"] if c["status"] == "active")
        body = {"line": line, "fixed_line": fixed_line, "explanation": "شرح", "focus_losses": 2}
        response = client.post(
            f"{URL}/challenges/{active['id']}/answer", json=body, headers=student
        )
        assert response.status_code == 200, response.text
        return response.json()

    first = play(12, "if x<=0:")["challenges"][0]  # found and fixed (spacing ignored)
    assert (first["located"], first["fixed"], first["score"]) == (True, True, 100.0)
    assert first["answer"]["mutated_line"] == "    if x < 0:"  # revealed after answering
    second = play(12, "    total = x")["challenges"][1]  # found, wrong fix
    assert (second["located"], second["fixed"], second["score"]) == (True, False, 60.0)
    assert play(11, "")["score"] is not None
    final = client.get(f"{URL}/{pid}", headers=student).json()
    assert final["score"] == 53.3  # (100 + 60 + 0) / 3
    again = client.post(f"{URL}/challenges/{first['id']}/answer", headers=student,
                        json={"line": 12, "fixed_line": "x"})  # fmt: skip
    assert again.status_code == 409

    faculty = users["faculty"].headers
    result = client.get(f"/api/v1/fraud/{pid}/results", headers=faculty).json()
    part = next(c for c in result["components"] if c["factor"] == "comprehension")
    assert part["score"] == 53.3
    assert client.get(f"{URL}/{pid}", headers=faculty).json()["challenges"][0]["focus_losses"] == 2
    inbox = client.get("/api/v1/notifications", headers=faculty).json()["items"]
    assert any(n["kind"] == "fingerprint_done" and "53.3" in n["body"] for n in inbox)


def test_time_limit_one_attempt_and_staff_reset(client, users, course, analyzer):  # noqa: F811
    pid, _ = start(client, users, course, analyzer)
    student = users["student"].headers
    assert client.post(f"{URL}/{pid}/start", headers=student).status_code == 409
    opened = client.post(f"{URL}/{pid}/next", headers=student).json()["challenges"][0]
    with database.SessionLocal() as db:
        row = db.get(ComprehensionChallenge, __import__("uuid").UUID(opened["id"]))
        row.shown_at -= timedelta(seconds=fingerprint.SECONDS_PER_CHALLENGE + 60)
        db.commit()
    late = client.post(f"{URL}/challenges/{opened['id']}/answer", headers=student,
                       json={"line": 12, "fixed_line": "    if x <= 0:"})  # fmt: skip
    assert late.status_code == 409
    expired = client.get(f"{URL}/{pid}", headers=student).json()["challenges"][0]
    assert (expired["status"], expired["score"]) == ("expired", 0.0)

    assert client.delete(f"{URL}/{pid}", headers=student).status_code == 403
    assert client.delete(f"{URL}/{pid}", headers=users["faculty"].headers).status_code == 204
    assert client.get(f"{URL}/{pid}", headers=student).json()["started"] is False


def test_low_score_raises_a_flag_and_no_suitable_function(client, users, course, analyzer):  # noqa: F811
    analyzer.routes["/api/v1/challenge/mutations"] = (200, {"challenges": []})
    pid = submit(client, users["student"], course["id"]).json()["id"]
    student = users["student"].headers
    assert client.post(f"{URL}/{pid}/start", headers=student).status_code == 422

    analyzer.routes["/api/v1/challenge/mutations"] = (
        200,
        {"challenges": GENERATED["challenges"][:1]},
    )
    assert client.post(f"{URL}/{pid}/start", headers=student).status_code == 201
    active = client.post(f"{URL}/{pid}/next", headers=student).json()["challenges"][0]
    client.post(f"{URL}/challenges/{active['id']}/answer", headers=student,
                json={"line": 10, "fixed_line": ""})  # fmt: skip
    result = client.get(f"/api/v1/fraud/{pid}/results", headers=users["faculty"].headers).json()
    flag = next(f for f in result["flags"] if f["type"] == "comprehension")
    assert flag["severity"] == "High" and "زُرعت في كوده" in flag["evidence_ar"]
