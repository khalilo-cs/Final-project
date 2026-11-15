"""Endpoints for other services (service token only), not for browsers."""

import uuid
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.models.user import User
from app.routes.deps import DbSession

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])
_bearer = HTTPBearer(auto_error=False)


def require_service(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "role", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated") from exc
    if claims["type"] != "access" or claims["role"] != "service":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal service endpoint")


class LookupRequest(BaseModel):
    ids: list[uuid.UUID] = Field(max_length=1000)


class UserSummary(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    student_id: str | None
    email: str


@router.post(
    "/users/lookup", response_model=list[UserSummary], dependencies=[Depends(require_service)]
)
def lookup_users(data: LookupRequest, db: DbSession):
    """Names for a list of user ids (unknown ids are omitted)."""
    if not data.ids:
        return []
    users = db.scalars(select(User).where(User.id.in_(set(data.ids)))).all()
    return [
        UserSummary(
            id=u.id,
            username=u.username,
            full_name=u.full_name,
            student_id=u.student_id,
            email=u.email,
        )
        for u in users
    ]
