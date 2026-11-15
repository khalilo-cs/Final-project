import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.database import SessionLocal, engine
from app.engine import autolearn
from app.migrate import migrate
from app.routes import ai, viva

log = logging.getLogger(__name__)


def _learning_loop(stop: threading.Event, interval: int) -> None:
    """Keeps learning in the background: no one has to trigger it."""
    while not stop.wait(interval):
        try:
            with SessionLocal() as db:
                autolearn.run_cycle(db)
        except Exception:  # noqa: BLE001 - one failed round must not stop learning
            log.exception("learning cycle failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate(engine)
    with SessionLocal() as db:
        autolearn.seed_builtin(db)
    stop = threading.Event()
    interval = get_settings().auto_learn_interval_seconds
    if interval > 0:
        threading.Thread(target=_learning_loop, args=(stop, interval), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="AI Project Examiner — Viva Engine", version="0.2.0", lifespan=lifespan)
app.include_router(viva.router)
app.include_router(ai.router)
app.include_router(ai.internal)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "viva-engine"}
