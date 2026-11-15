"""Things a faculty member should look at first (FR-10.6)."""

from app.models.project import Project, ProjectStatus
from app.services.grading import ProjectResults

PLAGIARISM_HIGH = 30.0
PLAGIARISM_MEDIUM = 15.0
_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def project_alerts(project: Project, results: ProjectResults) -> list[dict]:
    alerts = []

    def add(kind: str, severity: str, message: str) -> None:
        alerts.append(
            {
                "type": kind,
                "severity": severity,
                "message": message,
                "project_id": str(project.id),
                "project_title": project.title,
                "student_id": str(project.student_id),
                "course_id": str(project.course_id),
            }
        )

    if project.status is ProjectStatus.analysis_failed:
        add("analysis_failed", "Medium", f"Analysis failed: {project.analysis_error}")
    if results.report:
        percentage = results.report.plagiarism_percentage
        if percentage >= PLAGIARISM_MEDIUM:
            add(
                "plagiarism",
                "High" if percentage >= PLAGIARISM_HIGH else "Medium",
                f"{percentage}% of the report matches other submitted reports",
            )
        serious = [i for i in results.report.inconsistencies if i.get("severity") == "Medium"]
        if serious:
            claims = "; ".join(i.get("report_claim", "") for i in serious[:3])
            add("report_inconsistency", "Medium", f"Report contradicts the code: {claims}")
    if results.security and results.security.critical_count:
        add(
            "critical_vulnerability",
            "High",
            f"{results.security.critical_count} critical security vulnerabilities",
        )
    if (authenticity := results.authenticity) and authenticity["authenticity_score"] is not None:
        score = authenticity["authenticity_score"]
        serious = [f for f in authenticity["flags"] if f["severity"] in ("High", "Medium")]
        if score < 50 or any(f["severity"] == "High" for f in serious):
            add(
                "authenticity",
                "High",
                f"Authenticity {score}/100: " + "; ".join(f["evidence"] for f in serious[:2]),
            )
        elif serious:
            add("authenticity", "Medium", "; ".join(f["evidence"] for f in serious[:2]))
    if results.ai_fixes:
        add(
            "ai_fixes_applied",
            "Low",
            f"The student applied {results.ai_fixes} AI-proposed fixes; the original code "
            "is kept and the fixes are listed with the project",
        )
    if results.database and results.database.missing_primary_keys:
        tables = ", ".join(results.database.missing_primary_keys[:5])
        add("database_design", "Low", f"Tables without a primary key: {tables}")
    return alerts


def sort_alerts(alerts: list[dict]) -> list[dict]:
    return sorted(alerts, key=lambda a: (_ORDER.get(a["severity"], 9), a["project_title"]))
