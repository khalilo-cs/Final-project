"""Send a project's files to the analyzer services and store the results.

Runs as a FastAPI background task for now; moves to the RabbitMQ worker later.
Each analysis is independent: one failing does not discard the others' results.
"""

import json
import logging
import uuid
from pathlib import Path

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.project import (
    CodeAnalysisResult,
    DbAnalysisResult,
    FraudResult,
    Project,
    ProjectStatus,
    ReportAnalysisResult,
    SecurityAnalysisResult,
)
from app.services import internal_http, notify

log = logging.getLogger(__name__)


class AnalysisRejected(Exception):
    """The analyzer refused the input (bad archive / file); retrying will not help."""


def _post(base_url: str, path: str, file: Path, filename: str, data: dict | None = None) -> dict:
    with (
        internal_http.client(base_url, get_settings().analyzer_timeout_seconds) as http,
        open(file, "rb") as handle,
    ):
        response = http.post(path, files={"file": (filename, handle)}, data=data)
    if response.status_code in (400, 413, 422):
        raise AnalysisRejected(response.json().get("detail", "invalid file"))
    response.raise_for_status()
    return response.json()


# -- individual analyses -----------------------------------------------------------------


def _store_code(db: Session, project: Project) -> None:
    result = _post(
        get_settings().code_analyzer_url,
        "/api/v1/analysis/code",
        Path(project.code_path),
        "code.zip",
    )
    code, security = result["code"], result["security"]
    db.execute(delete(CodeAnalysisResult).where(CodeAnalysisResult.project_id == project.id))
    db.execute(
        delete(SecurityAnalysisResult).where(SecurityAnalysisResult.project_id == project.id)
    )
    db.add(
        CodeAnalysisResult(
            project_id=project.id,
            total_files=code["total_files"],
            total_lines=code["total_lines"],
            total_classes=code["total_classes"],
            total_functions=code["total_functions"],
            cyclomatic_complexity_avg=code["cyclomatic_complexity_avg"],
            cognitive_complexity_avg=code["cognitive_complexity_avg"],
            code_smells=code["code_smells"],
            overall_quality_score=code["overall_quality_score"],
            details=code,
            stack=result.get("stack") or {},
        )
    )
    db.add(
        SecurityAnalysisResult(
            project_id=project.id,
            vulnerabilities=security["vulnerabilities"],
            critical_count=security["critical_count"],
            high_count=security["high_count"],
            medium_count=security["medium_count"],
            low_count=security["low_count"],
            overall_security_score=security["overall_security_score"],
        )
    )
    if not project.programming_languages:
        project.programming_languages = sorted(code.get("languages", {}))


def _store_database(db: Session, project: Project) -> None:
    result = _post(
        get_settings().db_analyzer_url,
        "/api/v1/analysis/database",
        Path(project.db_schema_path),
        "schema.sql",
        data={"dialect": project.db_dialect or "mysql"},
    )
    db.execute(delete(DbAnalysisResult).where(DbAnalysisResult.project_id == project.id))
    db.add(
        DbAnalysisResult(
            project_id=project.id,
            total_tables=result["total_tables"],
            normalization_level=result["normalization_level"],
            missing_primary_keys=result["missing_primary_keys"],
            missing_foreign_keys=result["missing_foreign_keys"],
            missing_indexes=result["missing_indexes"],
            query_issues=result["query_issues"],
            er_diagram=result["er_diagram_mermaid"],
            overall_db_score=result["overall_db_score"],
            details=result,
        )
    )


def _store_fraud(db: Session, project: Project) -> None:
    # A student's own earlier submissions are not "copies".
    own = db.scalars(
        select(Project.id).where(Project.student_id == project.student_id, Project.id != project.id)
    ).all()
    result = _post(
        get_settings().fraud_detector_url,
        "/api/v1/fraud/analyze",
        Path(project.code_path),
        "code.zip",
        data={
            "document_id": str(project.id),
            "exclude_ids": json.dumps([str(i) for i in own]),
            "index": "true",
        },
    )
    db.execute(delete(FraudResult).where(FraudResult.project_id == project.id))
    db.add(
        FraudResult(
            project_id=project.id,
            code_similarity_max=result["similarity"]["max_similarity"],
            similar_projects=result["similarity"]["sources"],
            git_analysis=result["git"],
            style=result["style"],
            semantic=result.get("semantic"),
        )
    )


def _facts(db: Session, project: Project) -> dict | None:
    """What the code and database really contain, for the report consistency check."""
    code = db.scalar(select(CodeAnalysisResult).where(CodeAnalysisResult.project_id == project.id))
    if code is None:
        return None
    stack = code.stack or {}
    facts = {
        "languages": stack.get("languages", {}),
        "technologies": [t["name"] for t in stack.get("technologies", [])],
        "architecture": stack.get("architecture", []),
    }
    database = db.scalar(select(DbAnalysisResult).where(DbAnalysisResult.project_id == project.id))
    if database is not None:
        facts["total_tables"] = database.total_tables
    return facts


def _store_report(db: Session, project: Project) -> None:
    path = Path(project.report_path)
    facts = _facts(db, project)
    data = {"document_id": str(project.id), "index": "true"}
    if facts is not None:
        data["facts"] = json.dumps(facts)
    result = _post(
        get_settings().report_analyzer_url, "/api/v1/analysis/report", path, path.name, data
    )
    db.execute(delete(ReportAnalysisResult).where(ReportAnalysisResult.project_id == project.id))
    db.add(
        ReportAnalysisResult(
            project_id=project.id,
            plagiarism_percentage=result["plagiarism"]["plagiarism_percentage"],
            plagiarism_sources=result["plagiarism"]["sources"],
            inconsistencies=result["consistency"]["inconsistencies"],
            documentation_quality_score=result["documentation"]["documentation_quality_score"],
            overall_report_score=result["overall_report_score"],
            details=result,
        )
    )


def forget_report(project_id: uuid.UUID) -> None:
    """Remove a deleted project from the plagiarism and code-copy corpora (best effort)."""
    settings = get_settings()
    for url in (settings.report_analyzer_url, settings.fraud_detector_url):
        try:
            with internal_http.client(url, timeout=30) as http:
                http.delete(f"/api/v1/documents/{project_id}").raise_for_status()
        except httpx.HTTPError:
            log.warning("could not remove project %s from the index at %s", project_id, url)


# Order matters: the report check compares against the code and database results.
_ANALYSES = [
    ("Code", lambda project: True, _store_code),
    ("Database", lambda project: project.db_schema_path is not None, _store_database),
    ("Authenticity", lambda project: True, _store_fraud),
    ("Report", lambda project: project.report_path is not None, _store_report),
]


def run_analysis(project_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None:
            return
        errors = []
        for label, applies, store in _ANALYSES:
            if not applies(project):
                continue
            try:
                store(db, project)
                db.commit()
            except AnalysisRejected as exc:
                db.rollback()
                errors.append(f"{label} file rejected: {exc}")
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                db.rollback()
                log.exception("%s analysis failed for project %s", label, project_id)
                errors.append(f"{label} analyzer unavailable ({type(exc).__name__})")

        project = db.get(Project, project_id)
        if project is None:  # deleted while analyzing
            return
        project.status = ProjectStatus.analysis_failed if errors else ProjectStatus.analyzed
        project.analysis_error = "; ".join(errors) or None
        sent = _notify_analyzed(db, project)
        db.commit()
        notify.send_emails(sent)
        teach_viva_engine(db, project)
        from app.services.performance import start_run

        start_run(db, project)  # minutes-long: runs in the background on sandbox-runner


def _notify_analyzed(db: Session, project: Project) -> list:
    """Tell the student the result is ready, and the faculty member what needs attention."""
    from app.services.alerts import project_alerts
    from app.services.grading import load_results

    if project.status is ProjectStatus.analysis_failed:
        sent = notify.notify(
            db, [project.student_id], "analysis_failed", f"تعذّر تحليل «{project.title}»",
            "فشل جزء من التحليل؛ راجع صفحة المشروع أو أعد رفع الملفات.", project,
        )  # fmt: skip
    else:
        sent = notify.notify(
            db, [project.student_id], "analysis_done", f"اكتمل تحليل «{project.title}»",
            "النتائج والمستشار الذكي جاهزة، ويمكنك بدء المناقشة.", project,
        )  # fmt: skip
    serious = [
        a for a in project_alerts(project, load_results(db, project.id)) if a["severity"] == "High"
    ]
    if serious or project.status is ProjectStatus.analysis_failed:
        lines = [a["message_ar"] for a in serious[:5]] or [project.analysis_error or ""]
        sent += notify.notify(
            db, notify.course_faculty(db, project.course_id), "project_alert",
            f"يحتاج «{project.title}» إلى مراجعتك", "\n".join(lines), project,
        )  # fmt: skip
    return sent


def teach_viva_engine(db: Session, project: Project) -> None:
    """Every analyzed project is a lesson for the AI: send it automatically (best effort)."""
    from app.services.grading import load_results
    from app.services.viva_context import build_context

    try:
        context = build_context(project, load_results(db, project.id))
        internal_http.post_json(
            get_settings().viva_engine_url,
            "/internal/learn/project",
            {"project_id": str(project.id), "context": context},
            timeout=30,
        )
    except (httpx.HTTPError, ValueError):
        log.warning("viva-engine could not learn from project %s", project.id)
