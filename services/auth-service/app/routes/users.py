import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.models.user import Role, User
from app.routes.deps import CurrentUser, DbSession, require_roles
from app.schemas.auth import CreateUserRequest, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])

AdminOnly = Depends(require_roles(Role.admin))


@router.get("", response_model=list[UserOut], dependencies=[AdminOnly])
def list_users(
    db: DbSession,
    role: Role | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(User).order_by(User.created_at).limit(limit).offset(offset)
    if role is not None:
        query = query.where(User.role == role)
    return db.scalars(query).all()


@router.post(
    "", response_model=UserOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly]
)
def create_user(data: CreateUserRequest, db: DbSession):
    try:
        return auth_service.create_user(db, data, data.role)
    except auth_service.DuplicateUserError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Username or email already registered"
        ) from exc


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: DbSession, current: CurrentUser):
    if current.role is not Role.admin and current.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user
