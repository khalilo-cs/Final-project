import logging

from fastapi import FastAPI

from app.routes import analysis

# sqlglot warns on every vendor statement it falls back on; that is expected for dumps.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

app = FastAPI(title="AI Project Examiner — Database Analyzer", version="0.1.0")
app.include_router(analysis.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "db-analyzer"}
