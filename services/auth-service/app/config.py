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

    # -- University directory (LDAP / Active Directory) -------------------------------
    # Enabled when ldap_url is set. Users sign in with their directory username and
    # password on the normal login form; the account is created on first sign-in.
    ldap_url: str | None = None  # ldaps://dc.university.edu.ye:636 (or ldap:// + start_tls)
    ldap_start_tls: bool = True  # ignored for ldaps://
    ldap_ca_file: str | None = None  # the university CA, if not publicly trusted
    # Find the user with a service account (recommended) ...
    ldap_bind_dn: str | None = None
    ldap_bind_password: str | None = None
    ldap_base_dn: str | None = None  # ou=people,dc=university,dc=edu,dc=ye
    ldap_user_filter: str = "(|(uid={username})(sAMAccountName={username}))"
    # ... or bind directly with a DN template: uid={username},ou=people,dc=...
    ldap_user_dn_template: str | None = None
    ldap_email_attribute: str = "mail"
    ldap_name_attribute: str = "displayName"
    ldap_student_id_attribute: str | None = None  # e.g. employeeNumber
    # Members of these groups (memberOf DNs or group names) become faculty.
    # Admin rights are never granted through LDAP.
    ldap_faculty_groups: list[str] = []
    ldap_timeout_seconds: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
