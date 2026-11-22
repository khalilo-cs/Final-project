import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import audit, database
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
    plan_api,
    projects,
    reports,
    sandbox,
    uploads,
    viva,
)
from app.services import jobs

# Our own INFO lines (e.g. how long each analysis stage took) next to uvicorn's.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate(engine)
    stop = threading.Event()
    jobs.start_poller(stop)
    yield
    stop.set()


app = FastAPI(title="Mihakk — Project Service", version="0.1.0", lifespan=lifespan)
audit.install(app, lambda: database.SessionLocal())
app.include_router(audit.router)
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
app.include_router(plan_api.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "project-service"}
