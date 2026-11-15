"""Service configuration, read from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./auth.db"

    # No default on purpose: the service must not start with a guessable secret.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Optional first admin, created at startup when no admin exists yet.
    admin_username: str | None = None
    admin_email: str | None = None
    admin_password: str | None = None

    cors_origins: list[str] = []

    # Brute-force protection: lock an identifier after repeated failed logins.
    max_login_failures: int = 5
    lockout_minutes: int = 15

    # -- Single sign-on with the university's accounts (OpenID Connect) ---------------
    # Works with Microsoft Entra ID / Microsoft 365, Google Workspace, Keycloak, ...
    # Enabled when issuer, client id and secret are all set.
    public_url: str = "http://localhost:8080"  # where the web interface is served
    oidc_issuer: str | None = None  # e.g. https://login.microsoftonline.com/<tenant>/v2.0
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None  # default: {public_url}/svc/auth/api/v1/auth/oidc/callback
    oidc_display_name: str = "حساب الجامعة"
    oidc_scopes: str = "openid email profile"
    # Only these e-mail domains may sign in (empty = any address the provider vouches for).
    oidc_allowed_domains: list[str] = []
    # New accounts are students unless this claim (e.g. "roles" or "groups") contains
    # one of the faculty values. Admin rights are never granted through SSO.
    oidc_role_claim: str | None = None
    oidc_faculty_values: list[str] = []
    oidc_student_id_claim: str | None = None  # e.g. "employeeId"


@lru_cache
def get_settings() -> Settings:
    return Settings()
