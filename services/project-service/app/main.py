from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routes import analysis, courses, projects


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tables are created directly for now; Alembic migrations replace this later.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Project Examiner — Project Service", version="0.1.0", lifespan=lifespan)
app.include_router(courses.router)
app.include_router(projects.router)
app.include_router(analysis.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "project-service"}
