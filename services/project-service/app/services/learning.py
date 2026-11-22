"""What the system learns from the faculty's decisions (FR-12.2, FR-12.4).

1. Grading weights: when a faculty member approves final grades that differ from
   the suggestion, the weights that best reproduce *their* grades are fitted
   (non-negative, summing to 100) and offered for the course. With few graded
   projects the fit is pulled toward the current weights, so one odd grade does
   not swing everything.

2. Copy rings: pairwise similarity only says "A resembles B". Three or more
   projects linked to each other through similarity form a ring (one source
   shared around a group): a pattern no single pair shows.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grading import FinalGrade
from app.models.project import FraudResult, Project
from app.services import grading

MIN_GRADED = 5  # below this a fit is noise
PRIOR_STRENGTH = 10  # how many "virtual" projects the current weights count for
RING_THRESHOLD = 0.6  # similarity that links two projects into a ring
MIN_RING = 3


# ------------------------------------------------------------------ weights


def _project_to_simplex(values: list[float], total: float) -> list[float]:
    """Euclidean projection on {w >= 0, sum(w) = total} (Duchi et al., 2008)."""
    ordered = sorted(values, reverse=True)
    cumulative, theta = 0.0, 0.0
    for i, value in enumerate(ordered, start=1):
        cumulative += value
        candidate = (cumulative - total) / i
        if value - candidate > 0:
            theta = candidate
    return [max(v - theta, 0.0) for v in values]


def _fit(rows: list[tuple[list[float], float]], start: list[float]) -> list[float]:
    """Least squares on the simplex by projected gradient descent."""
    weights = list(start)
    n = len(rows)
    # Step size from the largest possible curvature (scores are 0-100, weights /100).
    scale = max(sum((s / 100) ** 2 for s in scores) for scores, _ in rows) or 1.0
    step = 0.9 / scale
    for _ in range(3000):
        gradient = [0.0] * len(weights)
        for scores, target in rows:
            error = sum(w * s / 100 for w, s in zip(weights, scores, strict=True)) - target
            for k, s in enumerate(scores):
                gradient[k] += 2 * error * s / 100 / n
        weights = _project_to_simplex(
            [w - step * g for w, g in zip(weights, gradient, strict=True)], 100.0
        )
    return weights


def _mae(rows, weights) -> float:
    return sum(
        abs(sum(w * s / 100 for w, s in zip(weights, scores, strict=True)) - target)
        for scores, target in rows
    ) / len(rows)


@dataclass
class LearnedWeights:
    graded_projects: int
    current: dict[str, float]
    suggested: dict[str, float] | None
    error_now: float | None  # mean |system - faculty| with the current weights
    error_suggested: float | None
    note_ar: str


def learn_weights(db: Session, course_id: uuid.UUID) -> LearnedWeights:
    current = grading.course_weights(db, course_id)
    criteria = [c for c, w in current.items() if w > 0]
    rows: list[tuple[list[float], float]] = []
    for final in db.scalars(
        select(FinalGrade)
        .join(Project, Project.id == FinalGrade.project_id)
        .where(Project.course_id == course_id)
    ):
        scores = final.scores or {}
        if all(scores.get(c) is not None for c in criteria):
            rows.append(([float(scores[c]) for c in criteria], final.faculty_adjusted_total))
    if len(rows) < MIN_GRADED or not criteria:
        note = f"يحتاج {MIN_GRADED} مشاريع على الأقل باعتماد نهائي وكل معاييرها مقيّمة."
        return LearnedWeights(len(rows), current, None, None, None, note)
    start = [current[c] for c in criteria]
    fitted = _fit(rows, start)
    blend = len(rows) / (len(rows) + PRIOR_STRENGTH)
    mixed = [blend * f + (1 - blend) * s for f, s in zip(fitted, start, strict=True)]
    rounded = [round(w) for w in mixed]
    rounded[rounded.index(max(rounded))] += 100 - sum(rounded)  # keep the total at 100
    suggested = {
        **{c: 0.0 for c in current},
        **dict(zip(criteria, map(float, rounded), strict=True)),
    }
    now, then = _mae(rows, start), _mae(rows, rounded)
    note = (
        f"الأوزان المقترحة تقرّب الدرجة المقترحة من درجاتكم المعتمدة: متوسط الفرق "
        f"{now:.1f} ← {then:.1f} درجة، من {len(rows)} مشروعاً."
        if then < now
        else "الأوزان الحالية تطابق درجاتكم المعتمدة بالفعل؛ لا حاجة للتغيير."
    )
    return LearnedWeights(len(rows), current, suggested if then < now else None,
                          round(now, 2), round(then, 2), note)  # fmt: skip


# ------------------------------------------------------------------ copy rings


def copy_rings(db: Session, course_id: uuid.UUID) -> list[dict]:
    projects = {
        str(p.id): p for p in db.scalars(select(Project).where(Project.course_id == course_id))
    }
    edges: dict[str, dict[str, float]] = {pid: {} for pid in projects}
    for fraud in db.scalars(
        select(FraudResult).where(FraudResult.project_id.in_([p.id for p in projects.values()]))
    ):
        me = str(fraud.project_id)
        sources = (fraud.similar_projects or []) + ((fraud.semantic or {}).get("sources") or [])
        for source in sources:
            other = str(source.get("document_id"))
            similarity = float(source.get("similarity") or 0)
            if other in projects and other != me and similarity >= RING_THRESHOLD:
                for a, b in ((me, other), (other, me)):
                    edges[a][b] = max(edges[a].get(b, 0.0), similarity)
    seen: set[str] = set()
    rings = []
    for start in edges:
        if start in seen or not edges[start]:
            continue
        group, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node in group:
                continue
            group.add(node)
            stack.extend(edges[node])
        seen |= group
        if len(group) >= MIN_RING:
            members = sorted(group, key=lambda pid: projects[pid].submitted_at)
            links = sorted(
                {(min(a, b), max(a, b), s) for a in group for b, s in edges[a].items()},
                key=lambda link: -link[2],
            )
            rings.append({
                "size": len(group),
                "projects": [{"project_id": pid, "title": projects[pid].title,
                              "student_id": str(projects[pid].student_id),
                              "submitted_at": projects[pid].submitted_at.isoformat()}
                             for pid in members],  # fmt: skip
                "links": [{"a": a, "b": b, "similarity": s} for a, b, s in links],
                "first_submitted": members[0],
                "message_ar": f"{len(group)} مشاريع مترابطة بالتشابه: قد يكون مصدر واحد "
                "تداوله عدة طلاب. أول من سلّم ليس بالضرورة صاحب العمل.",
            })  # fmt: skip
    return sorted(rings, key=lambda ring: -ring["size"])
