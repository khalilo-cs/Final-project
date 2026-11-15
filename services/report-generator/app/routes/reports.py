from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.render import render_pdf
from app.routes.deps import ServiceClaims

router = APIRouter(prefix="/internal/reports", tags=["reports"])


class StudentReport(BaseModel):
    audience: Literal["staff", "student"] = "student"
    project: dict
    student: dict = Field(default_factory=dict)
    course: str = ""
    grade: dict | None = None
    advice: dict | None = None
    code: dict | None = None
    security: dict | None = None
    database: dict | None = None
    report: dict | None = None
    viva: dict | None = None
    performance: dict | None = None
    authenticity: dict | None = None
    applied_fixes: list = Field(default_factory=list)


@router.post("/student")
def student_report(data: StudentReport, _: ServiceClaims):
    payload = data.model_dump()
    if data.audience == "student":
        payload["authenticity"] = None  # suspicion is never sent to the student
    return Response(render_pdf(payload), media_type="application/pdf")
