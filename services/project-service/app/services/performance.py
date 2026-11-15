"""Performance runs on sandbox-runner: start after analysis, collect when finished."""

import logging
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.project import PerformanceResult, Project
from app.services import internal_http

log = logging.getLogger(__name__)


def start_run(db: Session, project: Project) -> PerformanceResult:
    row = db.scalar(
        select(PerformanceResult).where(PerformanceResult.project_id == project.id)
    ) or PerformanceResult(project_id=project.id)
    row.details, row.overall_performance_score, row.runs_successfully = {}, None, None
    try:
        with (
            internal_http.client(get_settings().sandbox_runner_url, timeout=60) as http,
            open(Path(project.code_path), "rb") as archive,
        ):
            response = http.post("/internal/runs", files={"file": ("code.zip", archive)})
            response.raise_for_status()
        row.run_id, row.status, row.error = response.json()["run_id"], "running", None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # No Docker here (or runner down): the rest of the analysis is unaffected.
        log.warning("performance run not started for %s: %s", project.id, exc)
        row.run_id, row.status = None, "unavailable"
        row.error = "Performance testing is unavailable (sandbox runner or Docker not reachable)"
    db.add(row)
    db.commit()
    return row


def refresh(db: Session, project_id: uuid.UUID) -> PerformanceResult | None:
    row = db.scalar(select(PerformanceResult).where(PerformanceResult.project_id == project_id))
    if row is None or row.status != "running" or not row.run_id:
        return row
    try:
        with internal_http.client(get_settings().sandbox_runner_url, timeout=10) as http:
            response = http.get(f"/internal/runs/{row.run_id}")
        if response.status_code == 404:
            row.status, row.error = "lost", "The sandbox restarted; run the test again"
        else:
            response.raise_for_status()
            run = response.json()
            if run["status"] == "done":
                row.status = "done"
                row.runs_successfully = run.get("runs_successfully")
                row.overall_performance_score = run.get("overall_performance_score")
                row.error = run.get("error")
                row.details = run
        db.commit()
    except (httpx.HTTPError, ValueError):
        pass  # still running as far as we know; try again on the next read
    return row
