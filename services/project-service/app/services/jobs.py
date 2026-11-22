"""Durable queue for the heavy analysis work (NFR-03, NFR-05).

Every analysis request is a row in `analysis_jobs`, so nothing is lost when the
service restarts or the power goes out in the middle: on startup, jobs left
"running" by a dead process are put back in the queue and picked up again.

A job is claimed with one conditional UPDATE (queued -> running), so several
workers or replicas never run the same job twice. At most `analysis_workers`
jobs run at once per process; the rest wait their turn in the table.
"""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text, Uuid, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app import database
from app.config import get_settings
from app.database import Base

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


_slots: threading.Semaphore | None = None
_slots_lock = threading.Lock()


def _semaphore() -> threading.Semaphore:
    global _slots
    with _slots_lock:
        if _slots is None:
            _slots = threading.Semaphore(max(1, get_settings().analysis_workers))
        return _slots


def enqueue(db, project_id: uuid.UUID) -> AnalysisJob:
    """Queue an analysis (a still-queued job for the same project is reused)."""
    job = db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.project_id == project_id, AnalysisJob.status == "queued"
        )
    )
    if job is None:
        job = AnalysisJob(id=uuid.uuid4(), project_id=project_id)
        db.add(job)
    db.commit()
    return job


def _claim(db) -> AnalysisJob | None:
    for job_id in db.scalars(
        select(AnalysisJob.id)
        .where(AnalysisJob.status == "queued")
        .order_by(AnalysisJob.created_at)
        .limit(5)
    ):
        claimed = db.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == "queued")
            .values(
                status="running",
                started_at=datetime.now(UTC),
                attempts=AnalysisJob.attempts + 1,
            )
        ).rowcount
        db.commit()
        if claimed:
            return db.get(AnalysisJob, job_id)
    return None


def _finish(job_id: uuid.UUID, error: str | None) -> None:
    with database.SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        if error and job.attempts < MAX_ATTEMPTS:
            job.status, job.error = "queued", error  # try again later
        else:
            job.status = "failed" if error else "done"
            job.error, job.finished_at = error, datetime.now(UTC)
        db.commit()


def work() -> int:
    """Run queued jobs until the queue is empty or every slot is busy; returns how many ran."""
    from app.services.analysis_runner import run_analysis

    slots = _semaphore()
    done = 0
    while slots.acquire(blocking=False):
        try:
            with database.SessionLocal() as db:
                job = _claim(db)
                if job is None:
                    return done
                job_id, project_id = job.id, job.project_id
            try:
                run_analysis(project_id)
                _finish(job_id, None)
            except Exception as exc:  # noqa: BLE001 - recorded on the job, retried
                log.exception("analysis job %s failed", job_id)
                _finish(job_id, f"{type(exc).__name__}: {exc}"[:2000])
            done += 1
        finally:
            slots.release()
    return done


def recover(stale_after: timedelta = timedelta(minutes=30)) -> int:
    """Put back jobs whose worker died (service restart, power cut)."""
    limit = datetime.now(UTC) - stale_after
    with database.SessionLocal() as db:
        stale = db.scalars(select(AnalysisJob).where(AnalysisJob.status == "running")).all()
        count = 0
        for job in stale:
            started = job.started_at
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            if started is None or started < limit or get_settings().recover_all_running_jobs:
                job.status = "queued"
                count += 1
        db.commit()
    return count


def counts() -> dict[str, int]:
    with database.SessionLocal() as db:
        result: dict[str, int] = {}
        for status in db.scalars(select(AnalysisJob.status)):
            result[status] = result.get(status, 0) + 1
        return result


def start_poller(stop: threading.Event) -> threading.Thread | None:
    """Background loop: recover dead jobs at startup, then drain the queue regularly."""
    interval = get_settings().job_poll_seconds
    if interval <= 0:
        return None

    def loop():
        try:
            recovered = recover()
            if recovered:
                log.info("re-queued %d interrupted analysis jobs", recovered)
        except Exception:  # noqa: BLE001
            log.exception("job recovery failed")
        while not stop.is_set():
            try:
                while work():
                    pass
            except Exception:  # noqa: BLE001 - keep polling
                log.exception("job worker loop failed")
            stop.wait(interval)

    thread = threading.Thread(target=loop, name="analysis-jobs", daemon=True)
    thread.start()
    return thread


def wait_idle(timeout: float = 10) -> None:
    """Testing helper: block until no job is queued or running."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = counts()
        if not current.get("queued") and not current.get("running"):
            return
        time.sleep(0.05)
