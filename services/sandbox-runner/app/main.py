from fastapi import FastAPI

from app.routes import runs

app = FastAPI(title="Mihakk — Sandbox Runner", version="0.1.0")
app.include_router(runs.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "sandbox-runner"}
