"""Send a project's files to the analyzer services and store the results.

Runs as a FastAPI background task for now; moves to the RabbitMQ worker later.
Each analysis is independent: one failing does not discard the others' results.
"""

import logging
import time
import uuid
from pathlib import Path

import httpx
import jwt
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.project import (
    CodeAnalysisResult,
    DbAnalysisResult,
    Project,
    ProjectStatus,
    SecurityAnalysisResult,
)

log = logging.getLogger(__name__)

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


class AnalysisRejected(Exception):
    """The analyzer refused the input (bad archive / file); retrying will not help."""


def _service_token() -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "role": "service",
        "type": "access",
        "iat": now,
        "exp": now + 600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _post(base_url: str, path: str, file: Path, filename: str, data: dict | None = None) -> dict:
    with (
        httpx.Client(
            base_url=base_url,
            timeout=get_settings().analyzer_timeout_seconds,
            transport=transport,
        ) as client,
        open(file, "rb") as handle,
    ):
        response = client.post(
            path,
            files={"file": (filename, handle)},
            data=data,
            headers={"Authorization": f"Bearer {_service_token()}"},
        )
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


_ANALYSES = [
    ("Code", lambda project: True, _store_code),
    ("Database", lambda project: project.db_schema_path is not None, _store_database),
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
        db.commit()
