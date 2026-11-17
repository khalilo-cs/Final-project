"""Comprehension fingerprint: can the student find a defect seeded into their own code?

Scoring per challenge: 60 for pointing at the changed line, 40 more for restoring it.
An unanswered challenge scores 0 when its time runs out.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fingerprint import ComprehensionChallenge

SECONDS_PER_CHALLENGE = 240
GRACE_SECONDS = 10  # network delay
LOCATED_POINTS = 60.0
FIXED_POINTS = 40.0
CHALLENGES = 3


@dataclass(frozen=True)
class Profile:
    challenges: int
    seconds: int
    min_lines: int  # beginners write short functions


# First-year code is short and its authors read slower: fewer, longer challenges.
PROFILES = {
    "year1": Profile(2, 360, 4),
    "year2": Profile(3, 300, 5),
}
DEFAULT_PROFILE = Profile(CHALLENGES, SECONDS_PER_CHALLENGE, 6)


def profile(level: str | None) -> Profile:
    return PROFILES.get(level or "", DEFAULT_PROFILE)


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def normalize(line: str) -> str:
    return re.sub(r"\s+", "", line or "").rstrip(";")


def expire_overdue(db: Session, challenges: list[ComprehensionChallenge]) -> None:
    now, changed = datetime.now(UTC), False
    for challenge in challenges:
        limit = timedelta(seconds=challenge.seconds_allowed + GRACE_SECONDS)
        if challenge.status == "active" and now - _aware(challenge.shown_at) > limit:
            challenge.status, challenge.score = "expired", 0.0
            challenge.located = challenge.fixed = False
            challenge.seconds = challenge.seconds_allowed
            changed = True
    if changed:
        db.commit()


def load(db: Session, project_id: uuid.UUID) -> list[ComprehensionChallenge]:
    challenges = list(
        db.scalars(
            select(ComprehensionChallenge)
            .where(ComprehensionChallenge.project_id == project_id)
            .order_by(ComprehensionChallenge.position)
        )
    )
    expire_overdue(db, challenges)
    return challenges


def grade(challenge: ComprehensionChallenge, line: int, fixed_line: str) -> None:
    answer = challenge.answer
    challenge.located = line == answer["line"]
    challenge.fixed = challenge.located and normalize(fixed_line) == normalize(
        answer["original_line"]
    )
    challenge.score = LOCATED_POINTS * challenge.located + FIXED_POINTS * challenge.fixed


def session_score(challenges: list[ComprehensionChallenge]) -> float | None:
    """None until every challenge is answered or expired."""
    if not challenges or any(c.status in ("pending", "active") for c in challenges):
        return None
    return round(sum(c.score or 0.0 for c in challenges) / len(challenges), 1)
