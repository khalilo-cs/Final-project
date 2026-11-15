from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.migrate import migrate
from app.models import grading as _grading_models  # noqa: F401  (register tables)
from app.routes import (
    advice,
    analysis,
    courses,
    dashboard,
    fraud,
    grades,
    projects,
    reports,
    sandbox,
    viva,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tables are created directly for now; Alembic migrations replace this later.
    migrate(engine)
    yield


app = FastAPI(title="AI Project Examiner — Project Service", version="0.1.0", lifespan=lifespan)
app.include_router(courses.router)
app.include_router(projects.router)
app.include_router(analysis.router)
app.include_router(grades.router)
app.include_router(dashboard.router)
app.include_router(advice.router)
app.include_router(viva.router)
app.include_router(fraud.router)
app.include_router(sandbox.router)
app.include_router(reports.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "project-service"}
