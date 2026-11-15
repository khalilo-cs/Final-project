import logging

from fastapi import FastAPI

from app.routes import reports

logging.getLogger("weasyprint").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)

app = FastAPI(title="AI Project Examiner — Report Generator", version="0.1.0")
app.include_router(reports.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "report-generator"}
