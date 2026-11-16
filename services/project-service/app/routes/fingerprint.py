import uuid
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete

from app.config import get_settings
from app.models.fingerprint import ComprehensionChallenge
from app.models.project import Project, ProjectStatus
from app.routes.deps import CurrentPrincipal, DbSession, Principal
from app.services import access, fingerprint, internal_http, notify

router = APIRouter(prefix="/api/v1/fingerprint", tags=["comprehension fingerprint"])
_READY = (ProjectStatus.analyzed, ProjectStatus.viva_scheduled, ProjectStatus.viva_completed)


class Answer(BaseModel):
    line: int = Field(ge=1)
    fixed_line: Annotated[str, Field(max_length=2000)] = ""
    explanation: Annotated[str, Field(max_length=4000)] = ""
    focus_losses: int = Field(default=0, ge=0, le=1000)


def _challenge_out(challenge: ComprehensionChallenge, staff: bool) -> dict:
    done = challenge.status in ("answered", "expired")
    out = {
        "id": str(challenge.id),
        "position": challenge.position,
        "status": challenge.status,
        "file": challenge.file,
        "function": challenge.function,
        "language": challenge.language,
        "seconds_allowed": fingerprint.SECONDS_PER_CHALLENGE,
    }
    if challenge.status == "active" or done or staff:
        out |= {"code": challenge.code, "start_line": challenge.start_line}
    if challenge.status == "active":
        elapsed = (datetime.now(UTC) - fingerprint._aware(challenge.shown_at)).total_seconds()
        out["seconds_left"] = max(0, int(fingerprint.SECONDS_PER_CHALLENGE - elapsed))
    if done:
        out |= {
            "located": challenge.located,
            "fixed": challenge.fixed,
            "score": challenge.score,
            "seconds": challenge.seconds,
            "chosen_line": challenge.chosen_line,
            "fixed_line": challenge.fixed_line,
            "explanation": challenge.explanation,
        }
    if done or staff:  # the answer is revealed only when it can no longer help
        out["answer"] = challenge.answer
    if staff:
        out["focus_losses"] = challenge.focus_losses
    return out


def _state(challenges: list[ComprehensionChallenge], staff: bool) -> dict:
    return {
        "started": bool(challenges),
        "score": fingerprint.session_score(challenges),
        "challenges": [_challenge_out(c, staff) for c in challenges],
    }


def _own_project(db, principal: Principal, project_id: uuid.UUID) -> Project:
    project = access.get_project_for(db, principal, project_id)
    if project.student_id != principal.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the project's student")
    return project


@router.post("/{project_id}/start", status_code=status.HTTP_201_CREATED)
def start(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Prepare the challenges: one hidden defect in each of the student's main functions."""
    project = _own_project(db, principal, project_id)
    if project.status not in _READY:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Project is {project.status.value}")
    if fingerprint.load(db, project.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Already started; one attempt per project")
    try:
        with (
            internal_http.client(get_settings().code_analyzer_url, timeout=120) as http,
            open(project.code_path, "rb") as archive,
        ):
            response = http.post(
                "/api/v1/challenge/mutations",
                files={"file": ("code.zip", archive)},
                data={"count": fingerprint.CHALLENGES},
            )
            response.raise_for_status()
            generated = response.json()["challenges"]
    except (httpx.HTTPError, OSError, KeyError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Code analyzer unavailable"
        ) from exc
    if not generated:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No function in this project is suitable for the challenge",
        )
    for position, item in enumerate(generated, start=1):
        db.add(
            ComprehensionChallenge(
                project_id=project.id, position=position, file=item["file"],
                function=item["function"], language=item["language"],
                start_line=item["start_line"], code=item["code"], answer=item["mutation"],
            )
        )  # fmt: skip
    db.commit()
    return _state(fingerprint.load(db, project.id), staff=False)


@router.get("/{project_id}")
def state(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    project = access.get_project_for(db, principal, project_id)
    staff = project.student_id != principal.id
    return _state(fingerprint.load(db, project.id), staff)


@router.post("/{project_id}/next")
def open_next(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Show the next challenge; its clock starts now."""
    project = _own_project(db, principal, project_id)
    challenges = fingerprint.load(db, project.id)
    if not any(c.status == "active" for c in challenges):
        upcoming = next((c for c in challenges if c.status == "pending"), None)
        if upcoming is not None:
            upcoming.status, upcoming.shown_at = "active", datetime.now(UTC)
            db.commit()
    return _state(challenges, staff=False)


@router.post("/challenges/{challenge_id}/answer")
def answer(challenge_id: uuid.UUID, data: Answer, db: DbSession, principal: CurrentPrincipal):
    challenge = db.get(ComprehensionChallenge, challenge_id)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challenge not found")
    project = _own_project(db, principal, challenge.project_id)
    challenges = fingerprint.load(db, project.id)  # expires it when the time is over
    if challenge.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Challenge is {challenge.status}")
    now = datetime.now(UTC)
    fingerprint.grade(challenge, data.line, data.fixed_line)
    challenge.status, challenge.answered_at = "answered", now
    challenge.seconds = int((now - fingerprint._aware(challenge.shown_at)).total_seconds())
    challenge.chosen_line, challenge.fixed_line = data.line, data.fixed_line
    challenge.explanation, challenge.focus_losses = data.explanation, data.focus_losses
    sent = []
    if (score := fingerprint.session_score(challenges)) is not None:
        sent = notify.notify(
            db, notify.course_faculty(db, project.course_id), "fingerprint_done",
            f"أنهى الطالب تحدي بصمة الفهم في «{project.title}»",
            f"النتيجة {score:g} من 100.", project,
        )  # fmt: skip
    db.commit()
    notify.send_emails(sent)
    return _state(challenges, staff=False)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset(project_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Staff may allow a new attempt (e.g. after a power cut)."""
    project = access.get_project_for(db, principal, project_id)
    access.require_project_staff(db, principal, project)
    db.execute(
        delete(ComprehensionChallenge).where(ComprehensionChallenge.project_id == project.id)
    )
    db.commit()
