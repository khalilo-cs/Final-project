"""Suggested grade from the analysis results, with a justification (FR-10.7, FR-10.8)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.grading import FinalGrade, GradingCriterion
from app.models.project import (
    AiFixLog,
    CodeAnalysisResult,
    DbAnalysisResult,
    FraudResult,
    PerformanceResult,
    Project,
    ProjectStatus,
    ReportAnalysisResult,
    SecurityAnalysisResult,
    VivaLink,
)
from app.services import internal_http

# Default weights from the project plan (section 8). They sum to 100.
DEFAULT_WEIGHTS = {
    "code_quality": 20.0,
    "security": 10.0,
    "database": 10.0,
    "report": 15.0,
    "viva": 25.0,
    "authenticity": 10.0,
    "performance": 10.0,
}
# What each kind of work is graded on (weights sum to 100). A weekly assignment has no
# report or database to grade; a criterion with weight 0 is left out entirely.
WEIGHT_PRESETS = {
    "assignment": {
        "code_quality": 45.0, "security": 10.0, "database": 0.0, "report": 0.0,
        "viva": 30.0, "authenticity": 15.0, "performance": 0.0,
    },
    "course_project": {
        "code_quality": 25.0, "security": 10.0, "database": 15.0, "report": 10.0,
        "viva": 25.0, "authenticity": 10.0, "performance": 5.0,
    },
    "graduation": DEFAULT_WEIGHTS,
}  # fmt: skip
LEVELS_AR = {
    "year1": "السنة الأولى", "year2": "السنة الثانية", "year3": "السنة الثالثة",
    "year4": "السنة الرابعة", "postgrad": "الدراسات العليا",
}  # fmt: skip
KINDS_AR = {"assignment": "واجب برمجي", "course_project": "مشروع مادة", "graduation": "مشروع تخرج"}
CRITERIA = list(DEFAULT_WEIGHTS)
LABELS_AR = {
    "code_quality": "جودة الكود",
    "security": "الأمان",
    "database": "قاعدة البيانات",
    "report": "التقرير",
    "viva": "المناقشة",
    "authenticity": "أصالة المشروع",
    "performance": "الأداء",
}


@dataclass
class ProjectResults:
    code: CodeAnalysisResult | None = None
    security: SecurityAnalysisResult | None = None
    database: DbAnalysisResult | None = None
    report: ReportAnalysisResult | None = None
    viva_score: float | None = None
    viva_questions: int | None = None
    ai_fixes: int = 0
    fraud: FraudResult | None = None
    # Which similar projects were submitted after this one (they copied, not the reverse).
    later_projects: set[str] = field(default_factory=set)
    performance: PerformanceResult | None = None
    # Comprehension fingerprint: defects seeded into the student's own code (0-100).
    comprehension_score: float | None = None

    @property
    def authenticity(self) -> dict | None:
        from app.services.authenticity import compute

        return compute(self)


@dataclass
class Suggestion:
    weights: dict[str, float]
    scores: dict[str, float | None]
    suggested_total: float | None
    coverage: float  # % of the total weight that has a score
    missing: list[str]
    breakdown: list[dict] = field(default_factory=list)


def default_weights(kind: str | None) -> dict[str, float]:
    return dict(WEIGHT_PRESETS.get(kind or "graduation", DEFAULT_WEIGHTS))


def course_weights(db: Session, course_id: uuid.UUID) -> dict[str, float]:
    course = db.get(Course, course_id)
    weights = default_weights(course.kind if course is not None else None)
    for row in db.scalars(select(GradingCriterion).where(GradingCriterion.course_id == course_id)):
        if row.criterion in weights:
            weights[row.criterion] = row.weight
    return weights


def load_results(db: Session, project_id: uuid.UUID) -> ProjectResults:
    def one(model):
        return db.scalar(select(model).where(model.project_id == project_id))

    viva = latest_viva(db, project_id)
    fraud = one(FraudResult)
    later: set[str] = set()
    sources = (
        (fraud.similar_projects or []) + ((fraud.semantic or {}).get("sources") or [])
        if fraud
        else []
    )
    if sources:
        own = db.get(Project, project_id)
        ids = []
        for source in sources:
            try:
                ids.append(uuid.UUID(source["document_id"]))
            except (KeyError, ValueError):
                continue
        for other in db.scalars(select(Project).where(Project.id.in_(ids))):
            if own is not None and other.submitted_at > own.submitted_at:
                later.add(str(other.id))
    return ProjectResults(
        code=one(CodeAnalysisResult),
        security=one(SecurityAnalysisResult),
        database=one(DbAnalysisResult),
        report=one(ReportAnalysisResult),
        viva_score=viva.score if viva else None,
        fraud=fraud,
        later_projects=later,
        performance=_performance(db, project_id),
        comprehension_score=_comprehension(db, project_id),
        ai_fixes=db.scalar(
            select(func.count()).select_from(AiFixLog).where(AiFixLog.project_id == project_id)
        ),
    )


def _comprehension(db: Session, project_id: uuid.UUID) -> float | None:
    from app.services import fingerprint

    return fingerprint.session_score(fingerprint.load(db, project_id))


def _performance(db: Session, project_id: uuid.UUID) -> PerformanceResult | None:
    from app.services.performance import refresh

    return refresh(db, project_id)


def latest_viva(db: Session, project_id: uuid.UUID) -> VivaLink | None:
    """The newest completed viva, refreshing its score from viva-engine once it ends."""
    links = db.scalars(
        select(VivaLink)
        .where(VivaLink.project_id == project_id)
        .order_by(VivaLink.started_at.desc())
    ).all()
    for link in links:
        if link.status == "in_progress":
            summary = internal_http.viva_summary(link.session_id)
            if summary and summary["status"] != "in_progress":
                link.status, link.score = summary["status"], summary["overall_score"]
                project = db.get(Project, project_id)
                if summary["status"] == "completed" and project.status in (
                    ProjectStatus.analyzed,
                    ProjectStatus.viva_scheduled,
                ):
                    project.status = ProjectStatus.viva_completed
                db.commit()
        if link.status == "completed" and link.score is not None:
            return link
    return None


def _scores(results: ProjectResults) -> dict[str, float | None]:
    scores: dict[str, float | None] = dict.fromkeys(CRITERIA)
    if results.code:
        scores["code_quality"] = results.code.overall_quality_score
    if results.security:
        scores["security"] = results.security.overall_security_score
    if results.database:
        scores["database"] = results.database.overall_db_score
    if results.report:
        scores["report"] = results.report.overall_report_score
    scores["viva"] = results.viva_score
    authenticity = results.authenticity
    scores["authenticity"] = authenticity["authenticity_score"] if authenticity else None
    if results.performance and results.performance.status == "done":
        scores["performance"] = results.performance.overall_performance_score
    return scores


def _justify(criterion: str, results: ProjectResults) -> str | None:
    """One line explaining a score, built from the evidence behind it."""
    if criterion == "code_quality" and results.code:
        code = results.code
        return (
            f"{code.total_files} files, {code.total_lines} lines; average cyclomatic "
            f"complexity {code.cyclomatic_complexity_avg}; {len(code.code_smells)} code smells"
        )
    if criterion == "security" and results.security:
        sec = results.security
        if not sec.vulnerabilities:
            return "No vulnerabilities detected"
        kinds = sorted({v.get("type", "?") for v in sec.vulnerabilities})
        return (
            f"{sec.critical_count} critical, {sec.high_count} high, {sec.medium_count} medium, "
            f"{sec.low_count} low ({', '.join(kinds)})"
        )
    if criterion == "database" and results.database:
        database = results.database
        counts = database.details.get("issue_counts", {})
        issues = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "no issues"
        return (
            f"{database.total_tables} tables, estimated {database.normalization_level or '-'}; "
            f"{issues}"
        )
    if criterion == "report" and results.report:
        report = results.report
        return (
            f"plagiarism {report.plagiarism_percentage}%; "
            f"{len(report.inconsistencies)} report/code inconsistencies; "
            f"documentation {report.documentation_quality_score}/100"
        )
    if criterion == "authenticity" and (authenticity := results.authenticity):
        flags = "; ".join(f["evidence"] for f in authenticity["flags"][:2]) or "no warning signs"
        return f"{authenticity['coverage']}% of the evidence available; {flags}"
    if criterion == "performance" and results.performance:
        perf = results.performance
        if perf.status != "done":
            return perf.error or "performance test running"
        if not perf.runs_successfully:
            return f"the project does not run: {perf.error}"
        levels = perf.details.get("load_test") or []
        worst = levels[-1] if levels else {}
        return (
            f"starts in {perf.details.get('startup_seconds')}s; p95 {worst.get('p95_ms')} ms "
            f"with {worst.get('concurrent_users')} users; peak memory "
            f"{perf.details.get('memory_peak_mb')} MB"
        )
    if criterion == "viva" and results.viva_score is not None:
        return f"viva score {results.viva_score}/100 (adaptive questions on the student's code)"
    return None


def suggest(weights: dict[str, float], results: ProjectResults) -> Suggestion:
    scores = _scores(results)
    available = {c: s for c, s in scores.items() if s is not None and weights.get(c, 0) > 0}
    total_weight = sum(weights.values())
    covered = sum(weights[c] for c in available)
    suggested = None
    if covered > 0:
        # Average over what is known; `coverage` tells how much is still missing.
        suggested = round(sum(available[c] * weights[c] for c in available) / covered, 1)
    breakdown = [
        {
            "criterion": criterion,
            "label_ar": LABELS_AR[criterion],
            "weight": weights[criterion],
            "score": scores[criterion],
            "points": round(scores[criterion] * weights[criterion] / 100, 2)
            if scores[criterion] is not None
            else None,
            "justification": _justify(criterion, results),
        }
        for criterion in CRITERIA
    ]
    return Suggestion(
        weights=weights,
        scores=scores,
        suggested_total=suggested,
        coverage=round(100 * covered / total_weight, 1) if total_weight else 0.0,
        missing=[c for c in CRITERIA if c not in available and weights.get(c, 0) > 0],
        breakdown=breakdown,
    )


def project_suggestion(db: Session, project: Project) -> Suggestion:
    return suggest(course_weights(db, project.course_id), load_results(db, project.id))


def final_grade(db: Session, project_id: uuid.UUID) -> FinalGrade | None:
    return db.scalar(select(FinalGrade).where(FinalGrade.project_id == project_id))


def now_utc() -> datetime:
    return datetime.now(UTC)
