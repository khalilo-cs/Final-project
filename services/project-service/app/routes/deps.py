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
    id: uuid.UUID
    role: str
    token: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_faculty(self) -> bool:
        return self.role == "faculty"

    @property
    def is_student(self) -> bool:
        return self.role == "student"


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Verify the access token issued by auth-service."""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type", "role"]},
        )
        if claims["type"] != "access":
            raise unauthorized
        return Principal(uuid.UUID(claims["sub"]), claims["role"], credentials.credentials)
    except (jwt.PyJWTError, ValueError) as exc:
        raise unauthorized from exc


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")
