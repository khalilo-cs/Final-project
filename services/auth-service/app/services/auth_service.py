import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import LoginThrottle, RevokedToken, Role, User
from app.schemas.auth import RegisterRequest, TokenPair
from app.services import jwt_service

# Compared against when the user does not exist, so both paths cost one bcrypt check.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt())


class AuthError(Exception):
    pass


class LockedOut(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("locked")
        self.retry_after = retry_after


def _aware(moment: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; treat them as UTC.
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


def _check_lock(db: Session, identifier: str) -> None:
    row = db.get(LoginThrottle, identifier)
    locked_until = _aware(row.locked_until) if row else None
    if locked_until and locked_until > datetime.now(UTC):
        raise LockedOut(int((locked_until - datetime.now(UTC)).total_seconds()) + 1)


def _record_failure(db: Session, identifier: str) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    window = timedelta(minutes=settings.lockout_minutes)
    row = db.get(LoginThrottle, identifier) or LoginThrottle(
        identifier=identifier, failures=0, window_start=now
    )
    if now - _aware(row.window_start) > window:
        row.failures, row.window_start = 0, now
    row.failures += 1
    if row.failures >= settings.max_login_failures:
        row.locked_until, row.failures, row.window_start = now + window, 0, now
    db.merge(row)
    db.commit()


def _clear_failures(db: Session, identifier: str) -> None:
    db.execute(delete(LoginThrottle).where(LoginThrottle.identifier == identifier))
    db.commit()


class DuplicateUserError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode()
    if len(encoded) > 72:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


def create_user(db: Session, data: RegisterRequest, role: Role) -> User:
    user = User(
        username=data.username.lower(),
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        department=data.department,
        student_id=data.student_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateUserError from exc
    return user


def authenticate(db: Session, identifier: str, password: str) -> User:
    identifier = identifier.strip().lower()
    _check_lock(db, identifier)
    user = db.scalar(select(User).where(or_(User.username == identifier, User.email == identifier)))
    if user is None:
        bcrypt.checkpw(b"dummy-password", _DUMMY_HASH)
        _record_failure(db, identifier)
        raise AuthError
    if not verify_password(password, user.password_hash):
        _record_failure(db, identifier)
        raise AuthError
    _clear_failures(db, identifier)
    return user


def issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=jwt_service.create_access_token(user),
        refresh_token=jwt_service.create_refresh_token(user),
        expires_in=get_settings().access_token_minutes * 60,
    )


def _revoke(db: Session, payload: dict) -> None:
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(UTC)))
    db.merge(
        RevokedToken(
            jti=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    )
    db.commit()


def rotate_refresh_token(db: Session, refresh_token: str) -> TokenPair:
    """Exchange a refresh token for a new pair; the old one stops working."""
    try:
        payload = jwt_service.decode(refresh_token, jwt_service.REFRESH)
    except jwt_service.TokenError as exc:
        raise AuthError from exc
    if db.get(RevokedToken, payload["jti"]) is not None:
        raise AuthError
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise AuthError
    _revoke(db, payload)
    return issue_tokens(user)


def logout(db: Session, refresh_token: str) -> None:
    try:
        payload = jwt_service.decode(refresh_token, jwt_service.REFRESH)
    except jwt_service.TokenError:
        return  # already unusable
    _revoke(db, payload)


def ensure_admin(db: Session) -> None:
    settings = get_settings()
    if not (settings.admin_username and settings.admin_email and settings.admin_password):
        return
    if db.scalar(select(User).where(User.role == Role.admin)) is not None:
        return
    create_user(
        db,
        RegisterRequest(
            username=settings.admin_username,
            email=settings.admin_email,
            password=settings.admin_password,
            full_name="System Administrator",
        ),
        Role.admin,
    )
