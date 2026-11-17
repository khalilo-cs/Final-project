import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.engine import dialogue
from app.knowledge import store
from app.models import Review, VivaQA, VivaSession
from app.routes.deps import CurrentPrincipal, DbSession, Principal, parse_uuid, require_service

router = APIRouter(tags=["viva"])


class StartRequest(BaseModel):
    project_id: uuid.UUID
    student_id: uuid.UUID
    staff_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    language: Literal["ar", "en"] = "ar"
    context: dict


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    # Which question this answers. After a lost connection the browser sends the answer
    # again; if it had arrived the first time, the repeat must not answer the next one.
    question_number: int | None = Field(default=None, ge=1)


class ReviewRequest(BaseModel):
    score: float = Field(ge=0, le=100)
    verdict: Literal["correct", "partial", "wrong", "evasive"]
    notes: str | None = Field(default=None, max_length=4000)


def _state(db, session: VivaSession, principal: Principal | None = None) -> dict:
    current = session.current
    question = None
    if current:
        question = {
            "text": current["text"],
            "type": current["type"],
            "level": current["level"],
            "related_file": current["related_file"],
            "related_lines": current["related_lines"],
            "code": current.get("code"),
            "asked_at": current["asked_at"],
        }
    answered = dialogue.transcript(db, session)
    state = {
        "session_id": str(session.id),
        "project_id": str(session.project_id),
        "status": session.status,
        "language": session.language,
        "level": session.level,
        "question_number": len(answered) + (1 if current else 0),
        "max_questions": dialogue.max_questions(session),
        "current_question": question,
        "overall_score": session.overall_score,
        "providers": session.providers,
        "started_at": session.started_at.isoformat(),
        "seconds_left": dialogue.seconds_left(session) if session.status == "in_progress" else 0,
        "paused_seconds": session.paused_seconds or 0,
        "interruptions": len(session.pauses or []),
    }
    if principal is not None and principal.is_staff:
        state["pauses"] = session.pauses or []
    # Students do not see grading details during the viva, only afterwards.
    if principal is not None and (principal.is_staff or session.status != "in_progress"):
        state["transcript"] = answered
    return state


def _load(db, session_id: str, principal: Principal) -> VivaSession:
    session = db.get(VivaSession, parse_uuid(session_id))
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if principal.role == "service" or principal.role == "admin":
        return session
    if principal.id == str(session.student_id) or principal.id in session.staff_ids:
        return session
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")


# -- for project-service ---------------------------------------------------------------


@router.post("/internal/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    data: StartRequest, db: DbSession, _: Annotated[Principal, Depends(require_service)]
):
    session = dialogue.start_session(
        db, data.project_id, data.student_id, data.staff_ids, data.context, data.language
    )
    return _state(db, session)


@router.get("/internal/sessions/{session_id}")
def session_summary(
    session_id: str, db: DbSession, principal: Annotated[Principal, Depends(require_service)]
):
    session = _load(db, session_id, principal)
    return {
        "session_id": str(session.id),
        "status": session.status,
        "overall_score": session.overall_score,
        "questions": len(dialogue.transcript(db, session)),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }


# -- for the student and staff ---------------------------------------------------------


@router.get("/api/v1/viva/{session_id}")
def get_session(session_id: str, db: DbSession, principal: CurrentPrincipal):
    session = _load(db, session_id, principal)
    if principal.id == str(session.student_id):
        dialogue.touch(db, session)
    return _state(db, session, principal)


@router.post("/api/v1/viva/{session_id}/heartbeat")
def heartbeat(session_id: str, db: DbSession, principal: CurrentPrincipal):
    """Sent every few seconds while the viva page is open and online."""
    session = _load(db, session_id, principal)
    if principal.id != str(session.student_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the student")
    dialogue.touch(db, session)
    return {
        "status": session.status,
        "seconds_left": dialogue.seconds_left(session),
        "paused_seconds": session.paused_seconds or 0,
        "interruptions": len(session.pauses or []),
    }


@router.post("/api/v1/viva/{session_id}/answer")
def submit_answer(session_id: str, data: AnswerRequest, db: DbSession, principal: CurrentPrincipal):
    session = _load(db, session_id, principal)
    if principal.id != str(session.student_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the student answers")
    if session.status != "in_progress" or session.current is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The viva has ended")
    dialogue.touch(db, session)
    current_number = len(dialogue.transcript(db, session)) + 1
    if data.question_number is not None and data.question_number != current_number:
        return _state(db, session, principal)  # a repeat of an answer already received
    dialogue.answer(db, session, data.answer.strip())
    return _state(db, session, principal)


@router.post("/api/v1/viva/{session_id}/end")
def end_session(session_id: str, db: DbSession, principal: CurrentPrincipal):
    session = _load(db, session_id, principal)
    if session.status == "in_progress":
        dialogue.end(db, session)
    return _state(db, session, principal)


@router.get("/api/v1/viva/{session_id}/transcript")
def get_transcript(session_id: str, db: DbSession, principal: CurrentPrincipal):
    session = _load(db, session_id, principal)
    if not principal.is_staff and session.status == "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Available after the viva")
    return dialogue.transcript(db, session)


@router.put("/api/v1/viva/qa/{qa_id}/review")
def review_answer(qa_id: str, data: ReviewRequest, db: DbSession, principal: CurrentPrincipal):
    """A professor corrects the grade of one answer. This is what the system learns from."""
    qa = db.get(VivaQA, parse_uuid(qa_id))
    if qa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found")
    session = db.get(VivaSession, qa.session_id)
    if not (principal.role == "admin" or principal.id in session.staff_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found")
    review = db.query(Review).filter_by(qa_id=qa.id).one_or_none() or Review(qa_id=qa.id)
    review.faculty_id = uuid.UUID(principal.id)
    review.score, review.verdict, review.notes = data.score, data.verdict, data.notes
    db.add(review)
    # The reviewed pair also becomes knowledge the models can be shown later.
    store.add_item(
        db,
        "reviewed_qa",
        str(qa.id),
        f"Q: {qa.question}\nA: {qa.answer}\nProfessor score: {data.score} ({data.verdict})",
    )
    db.commit()
    return {"qa_id": str(qa.id), "score": review.score, "verdict": review.verdict}
