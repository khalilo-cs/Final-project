from collections import Counter

from fastapi import APIRouter
from sqlalchemy import select

from app.models.course import Course
from app.models.project import Project
from app.routes.deps import CurrentPrincipal, DbSession, forbidden
from app.services import grading, learning
from app.services.alerts import project_alerts, sort_alerts

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _staff_projects(db, principal) -> list[Project]:
    if principal.is_admin:
        return list(db.scalars(select(Project)))
    if principal.is_faculty:
        return list(
            db.scalars(select(Project).join(Course).where(Course.faculty_id == principal.id))
        )
    raise forbidden()


@router.get("/faculty/summary")
def summary(db: DbSession, principal: CurrentPrincipal):
    projects = _staff_projects(db, principal)
    statuses = Counter(project.status.value for project in projects)
    criterion_totals: dict[str, list[float]] = {c: [] for c in grading.CRITERIA}
    suggested, alert_count = [], 0
    for project in projects:
        results = grading.load_results(db, project.id)
        suggestion = grading.suggest(grading.course_weights(db, project.course_id), results)
        if suggestion.suggested_total is not None:
            suggested.append(suggestion.suggested_total)
        for criterion, score in suggestion.scores.items():
            if score is not None:
                criterion_totals[criterion].append(score)
        alert_count += len(project_alerts(project, results))

    def average(values):
        return round(sum(values) / len(values), 1) if values else None

    return {
        "total_projects": len(projects),
        "by_status": dict(statuses),
        "average_suggested_total": average(suggested),
        "average_by_criterion": {c: average(v) for c, v in criterion_totals.items()},
        "alerts": alert_count,
    }


@router.get("/faculty/alerts")
def alerts(db: DbSession, principal: CurrentPrincipal):
    found = []
    projects = _staff_projects(db, principal)
    for project in projects:
        found += project_alerts(project, grading.load_results(db, project.id))
    # Copy rings: a pattern only visible across a whole course (FR-12.4).
    for course_id in {p.course_id for p in projects}:
        for ring in learning.copy_rings(db, course_id):
            first = ring["projects"][0]
            found.append({
                "type": "copy_ring", "severity": "High",
                "message": f"{ring['size']} projects are linked by similarity (copy ring)",
                "message_ar": ring["message_ar"],
                "project_id": first["project_id"], "project_title": first["title"],
                "student_id": first["student_id"], "course_id": str(course_id),
                "ring": [p["project_id"] for p in ring["projects"]],
            })  # fmt: skip
    return sort_alerts(found)


_SMELL_AR = {
    "long_method": "دوال طويلة",
    "too_many_parameters": "معاملات كثيرة",
    "high_complexity": "تعقيد عالٍ",
    "deep_nesting": "تداخل عميق",
    "god_class": "كلاس ضخم",
    "duplicate_code": "كود مكرر",
    "dead_code": "كود غير مستخدم",
}
_DB_AR = {"missing_primary_key": "جدول بلا مفتاح أساسي", "missing_foreign_key": "مفتاح أجنبي مفقود",
          "repeating_group": "أعمدة مكررة (1NF)", "multivalued_column": "قيم متعددة في حقل (1NF)",
          "partial_dependency": "اعتماد جزئي (2NF)", "transitive_dependency": "اعتماد متعدٍّ (3NF)",
          "plaintext_password": "كلمات مرور كنص واضح", "float_for_money": "FLOAT للمال",
          "date_as_text": "تاريخ كنص", "phone_as_number": "هاتف كرقم"}  # fmt: skip


@router.get("/department/analytics")
def department_analytics(db: DbSession, principal: CurrentPrincipal):
    """FR-11: common mistakes, grade distribution, technologies, trends by term."""
    projects = _staff_projects(db, principal)
    issues: Counter = Counter()
    languages: Counter = Counter()
    technologies: Counter = Counter()
    distribution = [0] * 10
    by_term: dict[str, list[float]] = {}
    low_authenticity = graded = 0
    for project in projects:
        results = grading.load_results(db, project.id)
        suggestion = grading.suggest(grading.course_weights(db, project.course_id), results)
        final = grading.final_grade(db, project.id)
        total = final.faculty_adjusted_total if final else suggestion.suggested_total
        if total is not None:
            distribution[min(9, int(total // 10))] += 1
            course = db.get(Course, project.course_id)
            term = f"{course.year or ''} {course.semester or ''}".strip() or course.code
            by_term.setdefault(term, []).append(total)
        graded += final is not None
        if results.security:
            issues.update(f"أمان: {v['type']}" for v in results.security.vulnerabilities)
        if results.code:
            issues.update(
                f"كود: {_SMELL_AR.get(s['type'], s['type'])}" for s in results.code.code_smells
            )
            stack = results.code.stack or {}
            languages.update(stack.get("languages", {}).keys())
            technologies.update(t["name"] for t in stack.get("technologies", []))
        if results.database:
            for kind, count in results.database.details.get("issue_counts", {}).items():
                issues[f"قاعدة بيانات: {_DB_AR.get(kind, kind)}"] += count
        if results.report:
            issues.update("تقرير: تناقض مع الكود" for _ in results.report.inconsistencies)
        authenticity = results.authenticity
        if authenticity and (authenticity["authenticity_score"] or 100) < 50:
            low_authenticity += 1

    def ranked(counter: Counter, limit: int = 10) -> list[dict]:
        return [{"name": name, "count": count} for name, count in counter.most_common(limit)]

    return {
        "projects": len(projects),
        "graded": graded,
        "low_authenticity": low_authenticity,
        "low_authenticity_rate": round(100 * low_authenticity / len(projects), 1)
        if projects
        else 0,
        "common_issues": ranked(issues),
        "languages": ranked(languages, 8),
        "technologies": ranked(technologies, 10),
        "grade_distribution": [
            {"range": f"{i * 10}-{i * 10 + 9 if i < 9 else 100}", "count": n}
            for i, n in enumerate(distribution)
        ],
        "terms": [
            {"term": term, "projects": len(values), "average": round(sum(values) / len(values), 1)}
            for term, values in sorted(by_term.items())
        ],  # fmt: skip
    }
