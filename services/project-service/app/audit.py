"""Audit log of every state-changing request (NFR-02).

A middleware records who did what, when, from where and with which result, for
every POST/PUT/PATCH/DELETE and for downloads of student files. Request bodies
are never stored (they hold passwords, answers and code). Admins read the log at
GET /api/v1/audit.
"""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import JSON, DateTime, Integer, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.database import Base, get_db

log = logging.getLogger(__name__)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# Reads that hand out student files are audited too.
_SENSITIVE_READS = re.compile(r"/(code|export|excel|pdf|download)(\?|$|/)")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_SKIP = ("/health", "/api/v1/audit")


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)


def _actor(request: Request) -> tuple[uuid.UUID | None, str | None]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None, None
    settings = get_settings()
    try:
        claims = jwt.decode(header[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return uuid.UUID(claims["sub"]), claims.get("role")
    except (jwt.PyJWTError, KeyError, ValueError):
        return None, None


def _client_ip(request: Request) -> str | None:
    # nginx sets X-Real-IP; anything else could be forged by the caller.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def install(app: FastAPI, session_factory) -> None:
    """Register the middleware; `session_factory` opens a DB session (sessionmaker)."""

    @app.middleware("http")
    async def audit(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        wanted = request.method in _MUTATING or (
            request.method == "GET" and _SENSITIVE_READS.search(path)
        )
        if not wanted or path.startswith(_SKIP):
            return response
        actor_id, role = _actor(request)
        match = _UUID.search(path)
        entry = AuditEntry(
            actor_id=actor_id,
            actor_role=role,
            method=request.method,
            path=path[:500],
            target_id=uuid.UUID(match[0]) if match else None,
            status_code=response.status_code,
            ip=_client_ip(request),
            details={"query": str(request.url.query)[:300]} if request.url.query else None,
        )
        try:
            with session_factory() as db:
                db.add(entry)
                db.commit()
        except Exception:  # noqa: BLE001 - auditing must never break the request
            log.exception("audit write failed for %s %s", request.method, path)
        return response


_bearer = HTTPBearer(auto_error=False)


def _require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated") from exc
    if claims.get("type") != "access" or claims.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")


router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", dependencies=[Depends(_require_admin)])
def list_entries(
    db: Annotated[Session, Depends(get_db)],
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    if actor_id:
        query = query.where(AuditEntry.actor_id == actor_id)
    if target_id:
        query = query.where(AuditEntry.target_id == target_id)
    if since:
        query = query.where(AuditEntry.at >= since)
    return [
        {
            "id": e.id,
            "at": e.at.isoformat(),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "actor_role": e.actor_role,
            "method": e.method,
            "path": e.path,
            "target_id": str(e.target_id) if e.target_id else None,
            "status_code": e.status_code,
            "ip": e.ip,
            "details": e.details,
        }
        for e in db.scalars(query)
    ]
