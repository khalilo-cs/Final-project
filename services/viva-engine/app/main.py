from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routes import ai, viva


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Project Examiner — Viva Engine", version="0.1.0", lifespan=lifespan)
app.include_router(viva.router)
app.include_router(ai.router)
app.include_router(ai.internal)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "viva-engine"}
