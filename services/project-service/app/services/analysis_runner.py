"""Send a project's code to code-analyzer and store the results.

Runs as a FastAPI background task for now; moves to the RabbitMQ worker later.
"""

import logging
import time
import uuid
from pathlib import Path

import httpx
import jwt
from sqlalchemy import delete

from app.config import get_settings
from app.database import SessionLocal
from app.models.project import (
    CodeAnalysisResult,
    Project,
    ProjectStatus,
    SecurityAnalysisResult,
)

log = logging.getLogger(__name__)

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


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


def _call_analyzer(code_path: Path) -> dict:
    settings = get_settings()
    with (
        httpx.Client(
            base_url=settings.code_analyzer_url,
            timeout=settings.analyzer_timeout_seconds,
            transport=transport,
        ) as client,
        open(code_path, "rb") as archive,
    ):
        response = client.post(
            "/api/v1/analysis/code",
            files={"file": ("code.zip", archive, "application/zip")},
            headers={"Authorization": f"Bearer {_service_token()}"},
        )
    if response.status_code == 400:
        raise AnalysisRejected(response.json().get("detail", "invalid archive"))
    response.raise_for_status()
    return response.json()


class AnalysisRejected(Exception):
    """The analyzer refused the input (bad archive); retrying will not help."""


def run_code_analysis(project_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None:
            return
        try:
            result = _call_analyzer(Path(project.code_path))
        except AnalysisRejected as exc:
            _fail(db, project, f"Code archive rejected: {exc}")
            return
        except (httpx.HTTPError, ValueError) as exc:
            log.exception("code analysis failed for project %s", project_id)
            _fail(db, project, f"Code analyzer unavailable ({type(exc).__name__})")
            return

        code, security = result["code"], result["security"]
        db.execute(delete(CodeAnalysisResult).where(CodeAnalysisResult.project_id == project_id))
        db.execute(
            delete(SecurityAnalysisResult).where(SecurityAnalysisResult.project_id == project_id)
        )
        db.add(
            CodeAnalysisResult(
                project_id=project_id,
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
                project_id=project_id,
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
        project.status = ProjectStatus.analyzed
        project.analysis_error = None
        db.commit()


def _fail(db, project: Project, message: str) -> None:
    project.status = ProjectStatus.analysis_failed
    project.analysis_error = message
    db.commit()
