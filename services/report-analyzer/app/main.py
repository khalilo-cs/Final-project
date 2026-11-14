import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routes import analysis

logging.getLogger("pypdf").setLevel(logging.ERROR)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Project Examiner — Report Analyzer", version="0.1.0", lifespan=lifespan)
app.include_router(analysis.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "report-analyzer"}
