import json
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.config import get_settings
from app.parsers.extract import ExtractionError
from app.routes.deps import DbSession, ServiceClaims
from app.services.report_service import analyze_report

router = APIRouter(prefix="/api/v1", tags=["analysis"])

_MB = 1024 * 1024


@router.post("/analysis/report")
def analyze(
    file: UploadFile,
    db: DbSession,
    _: ServiceClaims,
    document_id: Annotated[str, Form(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    facts: Annotated[str | None, Form(description="JSON facts from code/db analysis")] = None,
    index: Annotated[bool, Form(description="Add to the plagiarism corpus")] = True,
):
    limit = get_settings().max_upload_mb * _MB
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Report is too large")
    parsed_facts = None
    if facts:
        try:
            parsed_facts = json.loads(facts)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "facts must be JSON"
            ) from exc
        if not isinstance(parsed_facts, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "facts must be an object")
    try:
        return analyze_report(db, document_id, data, file.filename or "", parsed_facts, index)
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget(document_id: str, db: DbSession, _: ServiceClaims):
    """Remove a report from the plagiarism corpus (e.g. the project was deleted)."""
    from app.analyzers.plagiarism import remove_document

    remove_document(db, document_id)
