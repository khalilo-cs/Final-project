import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import Role


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    student_id: str | None = Field(default=None, max_length=50)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, value: str) -> str:
        # bcrypt only hashes the first 72 bytes; reject instead of truncating silently.
        if len(value.encode()) > 72:
            raise ValueError("password must be at most 72 bytes")
        return value


class CreateUserRequest(RegisterRequest):
    role: Role


class LoginRequest(BaseModel):
    username: str = Field(description="Username or email")
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    full_name: str
    role: Role
    department: str | None
    student_id: str | None
    created_at: datetime
