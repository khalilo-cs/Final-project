"""Issue and verify the access / refresh JWT pair."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from app.models.user import User

ACCESS = "access"
REFRESH = "refresh"


class TokenError(Exception):
    pass


def _encode(user: User, token_type: str, lifetime: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user: User) -> str:
    return _encode(user, ACCESS, timedelta(minutes=get_settings().access_token_minutes))


def create_refresh_token(user: User) -> str:
    return _encode(user, REFRESH, timedelta(days=get_settings().refresh_token_days))


def decode(token: str, expected_type: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "jti", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload["type"] != expected_type:
        raise TokenError("wrong token type")
    return payload
