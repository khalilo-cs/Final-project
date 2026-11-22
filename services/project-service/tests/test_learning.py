import random
import uuid

from app import database
from app.models.grading import FinalGrade
from app.models.project import FraudResult
from app.services import learning
from tests.test_projects import course, submit  # noqa: F401 - fixture


def test_simplex_projection():
    weights = learning._project_to_simplex([50, 80, -10], 100)
    assert abs(sum(weights) - 100) < 1e-9 and min(weights) >= 0


def test_fit_recovers_the_weights_a_professor_really_uses():
    rng = random.Random(4)
    true = [60, 10, 30]  # the professor cares mostly about the first criterion
    rows = []
    for _ in range(40):
        scores = [rng.uniform(30, 100) for _ in true]
        rows.append((scores, sum(w * s / 100 for w, s in zip(true, scores, strict=True))))
    fitted = learning._fit(rows, [34, 33, 33])
    assert all(abs(f - t) < 2 for f, t in zip(fitted, true, strict=True))


def _grade(db, project_id, scores, total):
    db.add(FinalGrade(project_id=uuid.UUID(project_id), scores=scores, weights={},
                      suggested_total=None, faculty_adjusted_total=total,
                      graded_by=uuid.uuid4()))  # fmt: skip


def test_learned_weights_endpoint(client, users, course):  # noqa: F811
    staff = users["faculty"].headers
    url = f"/api/v1/courses/{course['id']}/criteria/learned"
    early = client.get(url, headers=staff).json()
    assert early["suggested"] is None and early["graded_projects"] == 0
    rng = random.Random(7)
    criteria = [c for c, w in early["current"].items() if w > 0]
    with database.SessionLocal() as db:
        for _ in range(30):
            pid = submit(client, users["student"], course["id"]).json()["id"]
            scores = {c: round(rng.uniform(40, 100)) for c in criteria}
            # This professor grades almost only on the viva.
            _grade(db, pid, scores, round(0.9 * scores["viva"] + 0.1 * scores["code_quality"], 1))
        db.commit()
    learned = client.get(url, headers=staff).json()
    assert learned["graded_projects"] == 30
    assert learned["error_suggested"] < learned["error_now"]
    assert sum(learned["suggested"].values()) == 100
    assert learned["suggested"]["viva"] > early["current"]["viva"]
    assert client.get(url, headers=users["student"].headers).status_code == 403


def test_copy_ring_of_three_is_found_and_alerted(client, users, course):  # noqa: F811
    ids = [submit(client, users["student"], course["id"]).json()["id"] for _ in range(4)]
    a, b, c, d = ids
    links = {a: [(b, 0.9)], b: [(c, 0.8)], c: [], d: [(a, 0.3)]}  # d is only weakly similar
    with database.SessionLocal() as db:
        for pid, sources in links.items():
            row = db.query(FraudResult).filter_by(project_id=uuid.UUID(pid)).one()
            row.similar_projects = [{"document_id": o, "similarity": s} for o, s in sources]
        db.commit()
    rings = client.get(f"/api/v1/fraud/course/{course['id']}/rings",
                       headers=users["faculty"].headers).json()  # fmt: skip
    assert len(rings) == 1 and rings[0]["size"] == 3
    assert {p["project_id"] for p in rings[0]["projects"]} == {a, b, c}
    alerts = client.get("/api/v1/dashboard/faculty/alerts", headers=users["faculty"].headers).json()
    assert any(alert["type"] == "copy_ring" for alert in alerts)
    assert client.get(f"/api/v1/fraud/course/{course['id']}/rings",
                      headers=users["student"].headers).status_code == 403  # fmt: skip
