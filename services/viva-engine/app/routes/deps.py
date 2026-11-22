import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

_bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class Principal:
    id: str
    role: str

    @property
    def is_staff(self) -> bool:
        return self.role in ("admin", "faculty")


def principal_from_token(token: str) -> Principal:
    """Raises HTTPException(401) for anything but a valid access token."""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type", "role"]},
        )
    except jwt.PyJWTError as exc:
        raise unauthorized from exc
    if claims["type"] != "access":
        raise unauthorized
    return Principal(str(claims["sub"]), claims["role"])


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal_from_token(credentials.credentials)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_service(principal: CurrentPrincipal) -> Principal:
    if principal.role != "service":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal service endpoint")
    return principal


def require_staff(principal: CurrentPrincipal) -> Principal:
    if not principal.is_staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return principal


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
