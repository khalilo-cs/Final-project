import uuid

import httpx
import pytest

from app.engine import autolearn, dialogue, learning
from app.knowledge import store
from app.models import BankQuestion, LearnedPoint, Topic, VivaQA, VivaSession
from tests.conftest import CONTEXT, token
from tests.test_viva import GOOD, FakeModel, answer

PROJECT = {
    **CONTEXT,
    "title": "متجر إلكتروني",
    "technologies": ["Laravel", "MySQL"],
    "functions": [{**CONTEXT["functions"][0], "code": "def secret_algorithm(): return 42"}],
}


class FakeTeacher(FakeModel):
    def _complete_json(self, system, prompt, schema, effort):
        self.prompts.append(prompt)
        if "explanation_ar" in schema["properties"]:
            return {
                "explanation_ar": "لارافيل إطار PHP يتبع نمط MVC.",
                "explanation_en": "Laravel is a PHP MVC framework.",
                "key_points": ["eloquent", "artisan"],
                "questions": [
                    {"language": "ar", "type": "technical", "level": 2,
                     "text": "ما دور Eloquent في مشروع Laravel؟", "expected_points": ["orm"]},
                    {"language": "en", "type": "technical", "level": 2,
                     "text": "What does artisan do?", "expected_points": ["cli"]},
                ],
            }  # fmt: skip
        return super()._complete_json(system, prompt, schema, effort)


def staff(people):
    return token(people["faculty"], "faculty")


def test_builtin_pack_loads_automatically_once(client, db, people):
    status = client.get("/api/v1/ai/status", headers=staff(people)).json()["auto_learning"]
    assert status["topics"] == 19
    assert status["question_bank"] == {"builtin": 26}
    assert status["knowledge_by_source"]["builtin"] == 38
    assert autolearn.seed_builtin(db) == 0  # idempotent
    events = client.get("/api/v1/ai/learning/events", headers=staff(people)).json()
    assert events[0]["kind"] == "builtin"


def test_learns_from_every_analyzed_project(client, db, people):
    service = token("svc", "service")
    body = {"project_id": "p1", "context": PROJECT}
    assert (
        client.post("/internal/learn/project", json=body, headers=staff(people)).status_code == 403
    )
    result = client.post("/internal/learn/project", json=body, headers=service).json()
    assert "tech:laravel" in result["new_topics"]
    assert (
        "vuln:sql_injection" in result["topics"]
        and "vuln:sql_injection" not in result["new_topics"]
    )
    laravel = db.get(Topic, "tech:laravel")
    assert (laravel.teacher_status, laravel.seen_in_projects) == ("pending", 1)
    client.post("/internal/learn/project", json=body, headers=service)
    db.expire_all()
    assert db.get(Topic, "tech:laravel").seen_in_projects == 2

    # Staff can search the project's code; question generation never sees it.
    hits = client.get("/api/v1/ai/knowledge/search", params={"q": "secret_algorithm"},
                      headers=staff(people)).json()  # fmt: skip
    assert hits and hits[0]["type"] == "project"
    private = store.search(db, "secret_algorithm", exclude_types=store.PRIVATE_SOURCES)
    assert private == []


def test_viva_uses_learned_questions_but_mostly_the_students_code(client, people):
    body = {"project_id": str(uuid.uuid4()), "student_id": str(people["student"]),
            "context": CONTEXT}  # fmt: skip
    state = client.post("/internal/sessions", json=body, headers=token("s", "service")).json()
    student = token(people["student"], "student")
    while state["status"] == "in_progress":
        state = answer(client, state["session_id"], GOOD, student).json()
    general = [qa for qa in state["transcript"] if qa["source"] == "builtin"]
    assert 1 <= len(general) <= dialogue.MAX_GENERAL_QUESTIONS
    # Everything else is generated from this project's own facts.
    specific = [qa for qa in state["transcript"] if qa["source"] == "template"]
    assert len(specific) >= 6
    assert any("calculate_fine" in qa["question"] for qa in specific)


def test_learns_key_points_and_agreed_grades_from_vivas(client, db, started, people, monkeypatch):
    session = db.get(VivaSession, uuid.UUID(started["session_id"]))
    # Strong answers to one question keep mentioning "transaction"; weak ones do not.
    for i, (text, score) in enumerate(
        [("we wrap the loan update in a transaction with rollback", 85),
         ("a transaction makes the fine update atomic", 90),
         ("inside one transaction both rows change", 80),
         ("not sure, it saves things", 20)]
    ):  # fmt: skip
        db.add(VivaQA(session_id=session.id, number=i + 1, template_key="k:fine",
                      question_type="technical", level=2, source="template",
                      question="How is the fine saved?", expected_points=["fine"],
                      answer=text, provider_scores={"template": score, "claude": score},
                      score=score, verdict="correct" if score > 70 else "wrong",
                      confidence=0.9))  # fmt: skip
    db.flush()
    result = autolearn.learn_from_session(db, session)
    db.commit()
    assert ("k:fine", "transaction") in result["new_points"]
    assert result["auto_labels"] == 4  # two graders agreed with high confidence
    assert autolearn.learned_points(db, "k:fine")[0] == "transaction"
    assert db.get(LearnedPoint, ("k:fine", "transaction")).support == 3

    # A new answer like an agreed one is now graded from that memory.
    memory = learning.memory_evaluation(db, "k:fine", "a transaction makes the fine update atomic")
    assert memory is not None and memory["score"] == 90.0


def test_background_cycle_fetches_docs_and_asks_the_teacher(client, db, people, monkeypatch):
    teacher = FakeTeacher("claude")
    monkeypatch.setattr(dialogue, "PROVIDERS", [teacher])
    monkeypatch.setattr(store, "check_public_address", False)
    monkeypatch.setattr(store, "transport", httpx.MockTransport(
        lambda r: httpx.Response(200, text="User-agent: *\\nAllow: /")
        if r.url.path == "/robots.txt" else
        httpx.Response(200, text="<p>Flask routes map URLs to Python functions.</p>",
                       headers={"content-type": "text/html"})))  # fmt: skip
    service = token("svc", "service")
    client.post("/internal/learn/project",
                json={"project_id": "p1", "context": {**PROJECT, "technologies": ["Laravel", "Flask"]}},
                headers=service)  # fmt: skip

    assert (
        client.post("/api/v1/ai/learn/now", headers=token(people["student"], "student")).status_code
        == 403
    )
    assert client.post("/api/v1/ai/learn/now", headers=staff(people)).status_code == 202
    db.expire_all()
    laravel = db.get(Topic, "tech:laravel")
    assert laravel.teacher_status == "done" and laravel.learned_at is not None
    taught = db.query(BankQuestion).filter_by(topic="tech:laravel").all()
    assert {q.source for q in taught} == {"teacher:claude"} and len(taught) == 2
    assert db.get(Topic, "tech:flask").docs_status == "done"
    kinds = {
        e["kind"] for e in client.get("/api/v1/ai/learning/events", headers=staff(people)).json()
    }
    assert {"teacher", "web", "project"} <= kinds
    topics = {t["key"]: t for t in client.get("/api/v1/ai/topics", headers=staff(people)).json()}
    assert topics["tech:laravel"]["teacher_status"] == "done"

    # What the teacher model wrote is used by the viva but never exported for training.
    rows = client.get("/api/v1/ai/dataset.jsonl", headers=staff(people)).text
    assert "Eloquent" not in rows


def test_offline_the_built_in_engine_reuses_what_the_teacher_taught(
    client, db, people, monkeypatch
):
    monkeypatch.setattr(dialogue, "PROVIDERS", [FakeTeacher("claude")])
    service = token("svc", "service")
    client.post(
        "/internal/learn/project", json={"project_id": "p", "context": PROJECT}, headers=service
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(store, "check_public_address", False)
        patch.setattr(store, "transport", httpx.MockTransport(lambda r: httpx.Response(503)))
        autolearn.run_cycle(db)
    monkeypatch.setattr(dialogue, "PROVIDERS", [])  # Claude gone
    body = {"project_id": str(uuid.uuid4()), "student_id": str(people["student"]),
            "context": PROJECT}  # fmt: skip
    state = client.post("/internal/sessions", json=body, headers=service).json()
    pool = db.get(VivaSession, uuid.UUID(state["session_id"])).pool
    assert any(q["text"] == "ما دور Eloquent في مشروع Laravel؟" for q in pool)
