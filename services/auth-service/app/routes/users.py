import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.user import Role, User
from app.routes.deps import CurrentUser, DbSession, require_roles
from app.schemas.auth import CreateUserRequest, UpdateUserRequest, UserOut
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


@router.get(
    "/by-username/{username}",
    response_model=UserOut,
    dependencies=[Depends(require_roles(Role.admin, Role.faculty))],
)
def find_student(username: str, db: DbSession):
    """Faculty enrol students by username; only student accounts can be found this way."""
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or user.role is not Role.student:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: DbSession, current: CurrentUser):
    if current.role is not Role.admin and current.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def _admins(db) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == Role.admin))


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, data: UpdateUserRequest, db: DbSession, current: CurrentUser):
    """Admins edit anyone (incl. role); everyone else only their own profile fields."""
    is_admin = current.role is Role.admin
    if not is_admin and current.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    if not is_admin and (data.role is not None or data.email is not None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can change role or e-mail")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    changes = data.model_dump(exclude_unset=True)
    if (
        changes.get("role") not in (None, Role.admin)
        and user.role is Role.admin
        and _admins(db) <= 1
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "The last admin cannot lose admin rights")
    for name, value in changes.items():
        setattr(user, name, value.lower() if name == "email" and value else value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail already registered") from exc
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def delete_user(user_id: uuid.UUID, db: DbSession, current: CurrentUser):
    """Existing access tokens expire within minutes; refresh tokens stop working at once."""
    if current.id == user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admins cannot delete their own account")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.role is Role.admin and _admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "The last admin cannot be deleted")
    db.delete(user)
    db.commit()
