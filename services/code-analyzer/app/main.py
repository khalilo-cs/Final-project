from fastapi import FastAPI

from app.routes import analysis

app = FastAPI(title="AI Project Examiner — Code Analyzer", version="0.1.0")
app.include_router(analysis.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "code-analyzer"}
