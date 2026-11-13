from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routes import auth, users
from app.services import auth_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tables are created directly for now; Alembic migrations replace this later.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        auth_service.ensure_admin(db)
    yield


app = FastAPI(title="AI Project Examiner — Auth Service", version="0.1.0", lifespan=lifespan)

if get_settings().cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(users.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "auth-service"}
