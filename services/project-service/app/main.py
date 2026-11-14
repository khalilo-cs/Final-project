from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.models import grading as _grading_models  # noqa: F401  (register tables)
from app.routes import advice, analysis, courses, dashboard, grades, projects, viva


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tables are created directly for now; Alembic migrations replace this later.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Project Examiner — Project Service", version="0.1.0", lifespan=lifespan)
app.include_router(courses.router)
app.include_router(projects.router)
app.include_router(analysis.router)
app.include_router(grades.router)
app.include_router(dashboard.router)
app.include_router(advice.router)
app.include_router(viva.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "project-service"}
