"""The "AI brain" page: providers, what the system has learned, knowledge, dataset."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database import SessionLocal
from app.engine import advisor, autolearn, dialogue, learning
from app.knowledge import store
from app.models import (
    KnowledgeItem,
    KnowledgeSource,
    LearningEvent,
    Review,
    Topic,
    VivaQA,
    VivaSession,
)
from app.routes.deps import DbSession, Principal, require_service, require_staff

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
internal = APIRouter(prefix="/internal", tags=["internal"])

Staff = Annotated[Principal, Depends(require_staff)]


class SourceRequest(BaseModel):
    url: str = Field(min_length=8, max_length=1000)


class SummaryRequest(BaseModel):
    findings: dict
    language: Literal["ar", "en"] = "ar"


@router.get("/status")
def status(db: DbSession, _: Staff):
    def count(model):
        return db.scalar(select(func.count()).select_from(model))

    return {
        "providers": dialogue.provider_status(),
        "sessions": count(VivaSession),
        "answers": count(VivaQA),
        "professor_reviews": count(Review),
        "knowledge_items": count(KnowledgeItem),
        "auto_learning": autolearn.stats(db),
        "training_data_policy": (
            "The fine-tuning export contains professors' grades only; text written by "
            "external models is used at runtime but never exported for training."
        ),
    }


@router.get("/learning")
def learning_report(db: DbSession, _: Staff):
    calibrations = learning.calibrations(db)
    effectiveness = learning.question_effectiveness(db)
    ranked = sorted(
        effectiveness.items(), key=lambda kv: kv[1]["discrimination"] or -1, reverse=True
    )
    return {
        "provider_calibration": {
            name: {"bias": c.bias, "mean_error": c.mae, "reviews": c.reviews}
            for name, c in calibrations.items()
        },
        "most_revealing_questions": [{"key": k, **v} for k, v in ranked[:10]],
        "least_revealing_questions": [{"key": k, **v} for k, v in ranked[-5:]][::-1],
        "notes": (
            "bias = average (professor score - model score). Models are corrected by their "
            "bias and weighted by how closely they agree with professors. Discrimination = "
            "how well a question's score predicts the rest of the viva."
        ),
    }


@router.get("/knowledge/sources")
def list_sources(db: DbSession, _: Staff):
    return [
        {
            "id": str(s.id),
            "url": s.url,
            "status": s.status,
            "error": s.error,
            "items": s.items,
            "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
        }
        for s in db.scalars(select(KnowledgeSource).order_by(KnowledgeSource.url))
    ]


def _ingest(source_id) -> None:
    with SessionLocal() as db:
        source = db.get(KnowledgeSource, source_id)
        if source is not None:
            store.ingest_url(db, source)


@router.post("/knowledge/sources", status_code=202)
def add_source(data: SourceRequest, db: DbSession, principal: Staff, background: BackgroundTasks):
    """Teach the system from a documentation page (fetched in the background)."""
    url = data.url.strip()
    source = db.scalar(select(KnowledgeSource).where(KnowledgeSource.url == url))
    if source is None:
        import uuid as _uuid

        source = KnowledgeSource(url=url, added_by=_uuid.UUID(principal.id))
        db.add(source)
    source.status = "pending"
    db.commit()
    background.add_task(_ingest, source.id)
    return {"id": str(source.id), "url": source.url, "status": source.status}


@router.get("/knowledge/search")
def search_knowledge(db: DbSession, _: Staff, q: Annotated[str, Query(min_length=2)]):
    return [
        {"source": item.source_ref, "type": item.source_type, "title": item.title,
         "text": item.text[:500], "score": round(score, 2)}
        for item, score in store.search(db, q, k=10)
    ]  # fmt: skip


@router.get("/dataset.jsonl")
def dataset(db: DbSession, _: Staff):
    """Professor-reviewed answers as JSONL, for fine-tuning a local model."""
    rows = [json.dumps(row, ensure_ascii=False) + "\n" for row in learning.training_dataset(db)]
    return StreamingResponse(
        iter(rows),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=viva-training.jsonl"},
    )


@internal.post("/advice/summary")
def advice_summary(data: SummaryRequest, _: Annotated[Principal, Depends(require_service)]):
    return advisor.summarize(data.findings, data.language) or {"summary": None}


@router.get("/learning/events")
def learning_events(db: DbSession, _: Staff, limit: Annotated[int, Query(ge=1, le=200)] = 50):
    rows = db.scalars(select(LearningEvent).order_by(LearningEvent.created_at.desc()).limit(limit))
    return [
        {"kind": e.kind, "summary": e.summary, "details": e.details,
         "created_at": e.created_at.isoformat()}
        for e in rows
    ]  # fmt: skip


@router.get("/topics")
def topics(db: DbSession, _: Staff):
    return [
        {"key": t.key, "title": t.title, "source": t.source, "seen_in_projects": t.seen_in_projects,
         "docs_status": t.docs_status, "teacher_status": t.teacher_status,
         "learned_at": t.learned_at.isoformat() if t.learned_at else None}
        for t in db.scalars(select(Topic).order_by(Topic.seen_in_projects.desc(), Topic.key))
    ]  # fmt: skip


def _cycle() -> None:
    with SessionLocal() as db:
        autolearn.run_cycle(db)


@router.post("/learn/now", status_code=202)
def learn_now(_: Staff, background: BackgroundTasks):
    """Run a learning round now instead of waiting for the background schedule."""
    background.add_task(_cycle)
    return {"status": "started"}


class ProjectLesson(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    context: dict


@internal.post("/learn/project")
def learn_project(
    data: ProjectLesson, db: DbSession, _: Annotated[Principal, Depends(require_service)]
):
    """Called by project-service after every analysis: the system learns from it."""
    return autolearn.learn_from_project(db, data.project_id, data.context)
