from fastapi import APIRouter, HTTPException, status

from app.models.user import Role
from app.routes.deps import CurrentUser, DbSession
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_INVALID = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession):
    """Self-registration always creates a student; staff accounts are made by an admin."""
    try:
        return auth_service.create_user(db, data, Role.student)
    except auth_service.DuplicateUserError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Username or email already registered"
        ) from exc


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, db: DbSession):
    try:
        user = auth_service.authenticate(db, data.username, data.password)
    except auth_service.AuthError as exc:
        raise _INVALID from exc
    return auth_service.issue_tokens(user)


@router.post("/refresh-token", response_model=TokenPair)
def refresh_token(data: RefreshRequest, db: DbSession):
    try:
        return auth_service.rotate_refresh_token(db, data.refresh_token)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshRequest, db: DbSession):
    auth_service.logout(db, data.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
