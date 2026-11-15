"""Things a faculty member should look at first (FR-10.6). Every alert has an Arabic text."""

from app.models.project import Project, ProjectStatus
from app.services.grading import ProjectResults

PLAGIARISM_HIGH = 30.0
PLAGIARISM_MEDIUM = 15.0
_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def project_alerts(project: Project, results: ProjectResults) -> list[dict]:
    alerts = []

    def add(kind: str, severity: str, message: str, message_ar: str) -> None:
        alerts.append(
            {
                "type": kind,
                "severity": severity,
                "message": message,
                "message_ar": message_ar,
                "project_id": str(project.id),
                "project_title": project.title,
                "student_id": str(project.student_id),
                "course_id": str(project.course_id),
            }
        )

    if project.status is ProjectStatus.analysis_failed:
        error = project.analysis_error
        add("analysis_failed", "Medium", f"Analysis failed: {error}", f"فشل التحليل: {error}")

    if results.report:
        percentage = results.report.plagiarism_percentage
        if percentage >= PLAGIARISM_MEDIUM:
            add(
                "plagiarism",
                "High" if percentage >= PLAGIARISM_HIGH else "Medium",
                f"{percentage}% of the report matches other submitted reports",
                f"{percentage}% من التقرير يطابق تقارير أخرى",
            )
        serious = [i for i in results.report.inconsistencies if i.get("severity") == "Medium"]
        if serious:
            claims = "; ".join(i.get("report_claim", "") for i in serious[:3])
            add(
                "report_inconsistency",
                "Medium",
                f"Report contradicts the code: {claims}",
                f"التقرير يناقض الكود: {claims}",
            )

    if results.security and results.security.critical_count:
        count = results.security.critical_count
        add(
            "critical_vulnerability",
            "High",
            f"{count} critical security vulnerabilities",
            f"{count} ثغرات أمنية حرجة",
        )

    authenticity = results.authenticity
    if authenticity and authenticity["authenticity_score"] is not None:
        score = authenticity["authenticity_score"]
        serious = [f for f in authenticity["flags"] if f["severity"] in ("High", "Medium")]
        english = "; ".join(f["evidence"] for f in serious[:2])
        arabic = "؛ ".join(f.get("evidence_ar", f["evidence"]) for f in serious[:2])
        if score < 50 or any(f["severity"] == "High" for f in serious):
            add(
                "authenticity",
                "High",
                f"Authenticity {score}/100: {english}",
                f"الأصالة {score}/100: {arabic}",
            )
        elif serious:
            add("authenticity", "Medium", english, arabic)

    performance = results.performance
    if performance and performance.status == "done" and not performance.runs_successfully:
        error = performance.error
        add(
            "does_not_run",
            "High",
            f"The project does not run: {error}",
            f"المشروع لا يعمل: {error}",
        )

    if results.ai_fixes:
        add(
            "ai_fixes_applied",
            "Low",
            f"The student applied {results.ai_fixes} AI-proposed fixes; the original code "
            "is kept and the fixes are listed with the project",
            f"طبّق الطالب {results.ai_fixes} إصلاحات اقترحها الذكاء الاصطناعي؛ الكود الأصلي "
            "محفوظ والإصلاحات مسجّلة مع المشروع",
        )

    if results.database and results.database.missing_primary_keys:
        tables = ", ".join(results.database.missing_primary_keys[:5])
        add(
            "database_design",
            "Low",
            f"Tables without a primary key: {tables}",
            f"جداول بلا مفتاح أساسي: {tables}",
        )
    return alerts


def sort_alerts(alerts: list[dict]) -> list[dict]:
    return sorted(alerts, key=lambda a: (_ORDER.get(a["severity"], 9), a["project_title"]))
