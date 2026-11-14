"""How the system learns from its own experience.

1. Memory: answers a professor already graded are reused to grade similar new answers.
2. Calibration: each model's bias against the professors' grades is measured and
   corrected; models that agree with professors more get more weight.
3. Question effectiveness: question types whose scores predict a student's overall
   viva result (they separate real understanding from guessing) are asked more.
4. Dataset: everything reviewed can be exported to fine-tune the university's own model.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.knowledge.bm25 import jaccard
from app.models import Review, VivaQA, VivaSession

MEMORY_MIN_SIMILARITY = 0.45


@dataclass
class Calibration:
    bias: float  # mean(professor - provider)
    mae: float  # mean absolute error after the bias correction
    reviews: int


def reviewed_examples(db: Session, template_key: str | None = None, limit: int = 200) -> list:
    """(qa, review) pairs, newest first."""
    query = select(VivaQA, Review).join(Review, Review.qa_id == VivaQA.id)
    if template_key:
        query = query.where(VivaQA.template_key == template_key)
    return list(db.execute(query.order_by(Review.created_at.desc()).limit(limit)).all())


def memory_evaluation(db: Session, template_key: str, answer: str):
    """Score from the most similar professor-graded answers to the same question type."""
    neighbours = []
    for qa, review in reviewed_examples(db, template_key):
        similarity = jaccard(qa.answer, answer)
        if similarity >= MEMORY_MIN_SIMILARITY:
            neighbours.append((similarity, review))
    if not neighbours:
        return None
    total = sum(s for s, _ in neighbours)
    score = sum(s * r.score for s, r in neighbours) / total
    best = max(neighbours, key=lambda item: item[0])
    return {
        "score": round(score, 1),
        "similarity": round(best[0], 2),
        "neighbours": len(neighbours),
        "verdict": best[1].verdict,
    }


def calibrations(db: Session) -> dict[str, Calibration]:
    errors: dict[str, list[float]] = defaultdict(list)
    for qa, review in reviewed_examples(db, limit=2000):
        for provider, score in (qa.provider_scores or {}).items():
            if provider != "memory" and score is not None:
                errors[provider].append(review.score - score)
    minimum = get_settings().min_reviews_for_calibration
    result = {}
    for provider, diffs in errors.items():
        if len(diffs) < minimum:
            continue
        bias = sum(diffs) / len(diffs)
        mae = sum(abs(d - bias) for d in diffs) / len(diffs)
        result[provider] = Calibration(round(bias, 2), round(mae, 2), len(diffs))
    return result


def combine(provider_scores: dict[str, float], db: Session, memory: dict | None) -> tuple:
    """Calibrated, accuracy-weighted ensemble. Returns (score, confidence, details)."""
    known = calibrations(db)
    weighted, total_weight, corrected = 0.0, 0.0, {}
    for provider, score in provider_scores.items():
        calibration = known.get(provider)
        value = score + calibration.bias if calibration else score
        value = max(0.0, min(100.0, value))
        # Weight = 1 / (error + 5): trust grows as a provider agrees with professors.
        weight = 1 / (calibration.mae + 5) if calibration else 1 / 20
        corrected[provider] = round(value, 1)
        weighted += weight * value
        total_weight += weight
    if memory:
        # Professors' own past grades on near-identical answers count strongly.
        weight = memory["similarity"] * memory["neighbours"] ** 0.5 / 5
        weighted += weight * memory["score"]
        total_weight += weight
        corrected["memory"] = memory["score"]
    score = weighted / total_weight if total_weight else 0.0
    values = list(corrected.values())
    spread = (max(values) - min(values)) if len(values) > 1 else 40.0
    confidence = max(0.2, min(0.95, 1 - spread / 100)) * (0.85 if len(values) == 1 else 1)
    return round(score, 1), round(confidence, 2), corrected


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def question_effectiveness(db: Session) -> dict[str, dict]:
    """Per question key: how well its score predicts the rest of the viva (discrimination)."""
    rows = db.execute(
        select(VivaQA.template_key, VivaQA.score, VivaQA.session_id)
        .join(VivaSession, VivaSession.id == VivaQA.session_id)
        .where(VivaSession.status == "completed")
    ).all()
    by_session: dict = defaultdict(list)
    for key, score, session_id in rows:
        by_session[session_id].append((key, score))
    pairs: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
    for answers in by_session.values():
        for index, (key, score) in enumerate(answers):
            others = [s for i, (_, s) in enumerate(answers) if i != index]
            if others:
                pairs[key][0].append(score)
                pairs[key][1].append(sum(others) / len(others))
    total = sum(len(xs) for xs, _ in pairs.values()) or 1
    stats = {}
    for key, (xs, ys) in pairs.items():
        discrimination = _pearson(xs, ys)
        # Upper confidence bound: rarely asked questions still get tried.
        exploration = math.sqrt(2 * math.log(total + 1) / len(xs))
        stats[key] = {
            "asked": len(xs),
            "average_score": round(sum(xs) / len(xs), 1),
            "discrimination": round(discrimination, 2) if discrimination is not None else None,
            "priority": round((discrimination or 0.3) + exploration, 3),
        }
    return stats


def good_question_examples(db: Session, limit: int = 6) -> list[dict]:
    """Past questions with the highest discrimination, as few-shot examples for models."""
    stats = question_effectiveness(db)
    best = sorted(
        (k for k, v in stats.items() if (v["discrimination"] or 0) >= 0.4),
        key=lambda k: stats[k]["discrimination"],
        reverse=True,
    )[:limit]
    examples = []
    for key in best:
        qa = db.scalar(select(VivaQA).where(VivaQA.template_key == key).limit(1))
        if qa:
            examples.append({"question": qa.question, "key": key})
    return examples


def graded_examples(db: Session, template_key: str, limit: int = 4) -> list[dict]:
    return [
        {"question": qa.question, "answer": qa.answer[:800], "score": review.score}
        for qa, review in reviewed_examples(db, template_key, limit)
    ]


def training_dataset(db: Session):
    """JSONL rows for fine-tuning a local model on the professors' own judgements."""
    for qa, review in reviewed_examples(db, limit=100000):
        yield {
            "messages": [
                {"role": "system", "content": "Grade a graduation project viva answer (0-100)."},
                {
                    "role": "user",
                    "content": f"Question: {qa.question}\nExpected: {qa.expected_points}\n"
                    f"Answer: {qa.answer}",
                },
                {
                    "role": "assistant",
                    "content": f'{{"score": {review.score}, "verdict": "{review.verdict}"}}',
                },
            ],
            "metadata": {
                "template_key": qa.template_key,
                "level": qa.level,
                "model_scores": qa.provider_scores,
                "professor_notes": review.notes,
            },
        }
