from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.migrate import migrate
from app.routes import analysis


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate(engine)
    yield


app = FastAPI(title="Mihakk — Fraud Detector", version="0.1.0", lifespan=lifespan)
app.include_router(analysis.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "fraud-detector"}
