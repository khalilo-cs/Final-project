import uuid
from datetime import UTC, datetime

from app import database
from app.services import analysis_runner, jobs
from tests.test_projects import course, submit  # noqa: F401 - fixture


def test_submission_runs_through_the_queue(client, users, course):  # noqa: F811
    project_id = submit(client, users["student"], course["id"]).json()["id"]
    with database.SessionLocal() as db:
        job = db.query(jobs.AnalysisJob).filter_by(project_id=uuid.UUID(project_id)).one()
        assert job.status == "done" and job.attempts == 1


def test_interrupted_job_is_recovered_and_finished(client, monkeypatch):
    ran = []
    monkeypatch.setattr(analysis_runner, "run_analysis", lambda pid: ran.append(pid))
    project_id = uuid.uuid4()
    with database.SessionLocal() as db:
        # What a power cut leaves behind: a job marked running by a dead process.
        db.add(jobs.AnalysisJob(id=uuid.uuid4(), project_id=project_id, status="running",
                                attempts=1, started_at=datetime.now(UTC)))  # fmt: skip
        db.commit()
    assert jobs.recover() == 1
    assert jobs.work() == 1
    assert ran == [project_id]
    assert jobs.counts() == {"done": 1}


def test_failing_job_is_retried_then_marked_failed(client, monkeypatch):
    calls = []

    def boom(pid):
        calls.append(pid)
        raise RuntimeError("analyzer exploded")

    monkeypatch.setattr(analysis_runner, "run_analysis", boom)
    with database.SessionLocal() as db:
        job = jobs.enqueue(db, uuid.uuid4())
    for _ in range(jobs.MAX_ATTEMPTS + 2):
        jobs.work()
    assert len(calls) == jobs.MAX_ATTEMPTS
    with database.SessionLocal() as db:
        stored = db.get(jobs.AnalysisJob, job.id)
        assert stored.status == "failed" and "analyzer exploded" in stored.error


def test_a_job_is_claimed_once(client):
    with database.SessionLocal() as db:
        job = jobs.enqueue(db, uuid.uuid4())
        assert jobs.enqueue(db, job.project_id).id == job.id  # still queued: reused
        first = jobs._claim(db)
        assert first is not None and first.id == job.id
        assert jobs._claim(db) is None
