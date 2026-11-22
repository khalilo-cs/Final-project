from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.config import get_settings
from app.parsers.mongo_parser import MongoSchemaError
from app.routes.deps import CurrentClaims
from app.services.database_analyzer import analyze_database

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_MB = 1024 * 1024


@router.post("/database")
def analyze(
    file: UploadFile,
    _: CurrentClaims,
    dialect: Annotated[Literal["mysql", "postgresql", "sqlite", "mongodb"], Form()] = "mysql",
):
    """Analyze a SQL schema / dump (or MongoDB JSON): keys, normalization, types, ER diagram."""
    limit = get_settings().max_upload_mb * _MB
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {get_settings().max_upload_mb} MB"
        )
    if b"\x00" in data[:8192]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected a text .sql / .json file")
    sql = data.decode("utf-8", errors="replace").lstrip("\ufeff")
    try:
        return analyze_database(sql, dialect)
    except MongoSchemaError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
