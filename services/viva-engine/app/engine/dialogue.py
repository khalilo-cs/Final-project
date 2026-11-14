"""The adaptive viva: pick a question, grade the answer, move the level, repeat."""

import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.engine import autolearn, learning
from app.knowledge import store
from app.models import VivaQA, VivaSession
from app.providers.base import Provider, ProviderError, Question
from app.providers.llm import ClaudeProvider, OllamaProvider, OpenAICompatibleProvider
from app.providers.template import TemplateProvider

log = logging.getLogger(__name__)

_TEMPLATE = TemplateProvider()
# Tests may replace these instances.
PROVIDERS: list[Provider] = [ClaudeProvider(), OllamaProvider(), OpenAICompatibleProvider()]
_LEVEL_WEIGHT = {1: 1.0, 2: 1.5, 3: 2.0, 4: 2.0}
MAX_GENERAL_QUESTIONS = 2


def active_providers() -> list[Provider]:
    return [p for p in PROVIDERS if p.available()]


def provider_status() -> list[dict]:
    status = [{"name": "template", "available": True, "kind": "built-in"}]
    for provider in PROVIDERS:
        status.append({"name": provider.name, "available": provider.available(), "kind": "model"})
    return status


def _as_dict(question: Question) -> dict:
    return asdict(question)


def _as_question(data: dict) -> Question:
    return Question(**data)


# -- session lifecycle -----------------------------------------------------------------


def start_session(
    db: Session,
    project_id: uuid.UUID,
    student_id: uuid.UUID,
    staff_ids: list[str],
    context: dict,
    language: str,
) -> VivaSession:
    settings = get_settings()
    examples = learning.good_question_examples(db)
    topics = " ".join(context.get("technologies", []) + [context.get("title", "")])
    knowledge = [
        item.text for item, _ in store.search(db, topics, k=5, exclude_types=store.PRIVATE_SOURCES)
    ]

    pool = _TEMPLATE.generate_questions(context, language, settings.max_questions * 2, [], [])
    # Questions the system learned (built-in pack, teacher models) for this project's topics.
    pool += autolearn.bank_questions(db, list(autolearn.topics_from_context(context)), language)
    used = ["template"]
    for provider in active_providers():
        try:
            pool += provider.generate_questions(
                context, language, settings.max_questions, examples, knowledge
            )
            used.append(provider.name)
        except ProviderError as exc:
            log.warning("%s could not write questions: %s", provider.name, exc)

    session = VivaSession(
        project_id=project_id,
        student_id=student_id,
        staff_ids=[str(s) for s in staff_ids],
        language=language,
        context=context,
        pool=[_as_dict(q) for q in pool],
        providers=used,
    )
    db.add(session)
    db.flush()
    _advance(db, session)
    db.commit()
    return session


def _answered(db: Session, session: VivaSession) -> list[VivaQA]:
    return list(
        db.scalars(select(VivaQA).where(VivaQA.session_id == session.id).order_by(VivaQA.number))
    )


def _pick(db: Session, session: VivaSession, previous: VivaQA | None) -> Question | None:
    asked = {(qa.template_key, qa.question) for qa in _answered(db, session)}
    candidates = [_as_question(q) for q in session.pool]
    candidates = [q for q in candidates if (q.key, q.text) not in asked]
    if not candidates:
        return None

    # An evasive or weak answer gets one verification follow-up on the same code (not a
    # chain of them: a struggling student goes back to their level afterwards).
    if (
        previous is not None
        and previous.verdict in ("evasive", "wrong")
        and previous.related_file
        and previous.question_type != "verification"
    ):
        follow_up = [
            q for q in candidates
            if q.type == "verification" and q.related_file == previous.related_file
        ]  # fmt: skip
        if follow_up:
            return follow_up[0]

    stats = learning.question_effectiveness(db)
    answered = _answered(db, session)
    asked_types = [qa.question_type for qa in answered]
    # General topic questions (from the knowledge bank) are a small part of a viva: the
    # point is questions only the author of this code can answer.
    general_asked = sum(1 for qa in answered if qa.template_key.startswith("bank:"))
    if general_asked >= MAX_GENERAL_QUESTIONS:
        candidates = [q for q in candidates if not q.key.startswith("bank:")] or candidates

    def rank(question: Question) -> tuple:
        distance = abs(question.level - session.level)
        repeated_type = asked_types[-1:] == [question.type]
        general = question.key.startswith("bank:")
        priority = stats.get(question.key, {}).get("priority", 1.0)
        model_written = question.source not in ("template", "builtin")
        return (distance, repeated_type, general, -priority, not model_written)

    return min(candidates, key=rank)


def _advance(db: Session, session: VivaSession, previous: VivaQA | None = None) -> None:
    settings = get_settings()
    answered = len(_answered(db, session))
    started = session.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    timed_out = datetime.now(UTC) - started > timedelta(minutes=settings.session_minutes)
    question = (
        None if answered >= settings.max_questions or timed_out else _pick(db, session, previous)
    )
    if question is None:
        _finish(db, session)
        return
    session.current = {**_as_dict(question), "asked_at": datetime.now(UTC).isoformat()}


def _finish(db: Session, session: VivaSession, status: str = "completed") -> None:
    answers = _answered(db, session)
    if answers:
        total = sum(_LEVEL_WEIGHT[qa.level] for qa in answers)
        session.overall_score = round(
            sum(qa.score * _LEVEL_WEIGHT[qa.level] for qa in answers) / total, 1
        )
    session.status = status if answers else "abandoned"
    session.current = None
    session.ended_at = datetime.now(UTC)
    if answers:
        autolearn.learn_from_session(db, session)


def answer(db: Session, session: VivaSession, text: str) -> VivaQA:
    current = session.current
    question = _as_question({k: v for k, v in current.items() if k != "asked_at"})
    asked_at = datetime.fromisoformat(current["asked_at"])

    # Key points learned from earlier strong answers count like the original ones.
    learned = [p for p in autolearn.learned_points(db, question.key)
               if p not in question.expected_points]  # fmt: skip
    graded = Question(**{**_as_dict(question),
                         "expected_points": question.expected_points + learned})  # fmt: skip
    template = _TEMPLATE.evaluate(graded, text, session.language, [])
    scores = {"template": template.score}
    reasons = {"template": template.reasoning}
    examples = learning.graded_examples(db, question.key)
    for provider in active_providers():
        try:
            evaluation = provider.evaluate(question, text, session.language, examples)
            scores[provider.name] = evaluation.score
            reasons[provider.name] = evaluation.reasoning
        except ProviderError as exc:
            log.warning("%s could not grade: %s", provider.name, exc)
    memory = learning.memory_evaluation(db, question.key, text)
    score, confidence, corrected = learning.combine(scores, db, memory)
    if template.verdict == "evasive" and score < 40:
        verdict = "evasive"
    else:
        verdict = "correct" if score >= 70 else "partial" if score >= 40 else "wrong"
    reasoning = " | ".join(f"{name}: {why}" for name, why in reasons.items() if why)
    if memory:
        reasoning += (
            f" | memory: {memory['neighbours']} similar answer(s) graded by professors "
            f"(similarity {memory['similarity']})"
        )

    number = (
        db.scalar(select(func.count()).select_from(VivaQA).where(VivaQA.session_id == session.id))
        + 1
    )
    qa = VivaQA(
        session_id=session.id,
        number=number,
        template_key=question.key,
        question_type=question.type,
        level=question.level,
        source=question.source,
        question=question.text,
        expected_points=question.expected_points,
        related_file=question.related_file,
        related_lines=question.related_lines,
        answer=text,
        provider_scores={**scores, **({"memory": memory["score"]} if memory else {})},
        score=score,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning[:4000],
        response_seconds=round((datetime.now(UTC) - asked_at).total_seconds(), 1),
    )
    db.add(qa)
    db.flush()

    # Adapt: strong answers raise the level, weak ones lower it.
    if score >= 75:
        session.level = min(4, session.level + 1)
    elif score < 40:
        session.level = max(1, session.level - 1)
    _advance(db, session, qa)
    db.commit()
    return qa


def end(db: Session, session: VivaSession) -> None:
    _finish(db, session)
    db.commit()


def transcript(db: Session, session: VivaSession) -> list[dict]:
    return [
        {
            "id": str(qa.id),
            "number": qa.number,
            "type": qa.question_type,
            "level": qa.level,
            "source": qa.source,
            "question": qa.question,
            "related_file": qa.related_file,
            "related_lines": qa.related_lines,
            "answer": qa.answer,
            "score": qa.score,
            "verdict": qa.verdict,
            "confidence": qa.confidence,
            "provider_scores": qa.provider_scores,
            "reasoning": qa.reasoning,
            "response_seconds": qa.response_seconds,
        }
        for qa in _answered(db, session)
    ]
