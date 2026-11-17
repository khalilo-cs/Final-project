from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.migrate import migrate
from app.models import fingerprint as _fingerprint_models  # noqa: F401
from app.models import grading as _grading_models  # noqa: F401  (register tables)
from app.models import notification as _notification_models  # noqa: F401
from app.models import upload as _upload_models  # noqa: F401
from app.routes import (
    advice,
    analysis,
    courses,
    dashboard,
    fingerprint,
    fraud,
    grades,
    notifications,
    projects,
    reports,
    sandbox,
    uploads,
    viva,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate(engine)
    yield


app = FastAPI(title="Mihakk — Project Service", version="0.1.0", lifespan=lifespan)
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
app.include_router(notifications.router)
app.include_router(fingerprint.router)
app.include_router(uploads.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "project-service"}
