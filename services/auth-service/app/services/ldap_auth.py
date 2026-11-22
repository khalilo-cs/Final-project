"""Sign-in with the university directory (LDAP / Active Directory), FR-01.4.

The student or faculty member types their directory username and password on the
normal login form. We verify them with an LDAP bind (never by reading a password
attribute), then create or update the local account linked as "ldap|<dn>".

Safety rules:
* empty passwords are rejected before any bind (an empty password is an
  "unauthenticated bind" that many servers accept as success);
* the username is escaped for both filters and DNs (no LDAP injection);
* the connection uses TLS (ldaps:// or StartTLS) unless explicitly configured;
* directory groups can make someone faculty, never admin.
"""

import logging
import secrets
import ssl
from dataclasses import dataclass

from ldap3 import ALL_ATTRIBUTES, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import escape_rdn
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.user import Role, User

log = logging.getLogger(__name__)

# Tests replace this with ldap3's offline MOCK_SYNC server.
server_factory = None
connection_strategy = "SYNC"


class LdapUnavailable(Exception):
    """The directory could not be reached; the caller falls back to local accounts."""


@dataclass
class DirectoryUser:
    dn: str
    username: str
    email: str | None
    full_name: str | None
    student_id: str | None
    groups: list[str]


def enabled(s: Settings | None = None) -> bool:
    s = s or get_settings()
    return bool(s.ldap_url) and bool(s.ldap_user_dn_template or s.ldap_base_dn)


def _server(s: Settings) -> Server:
    if server_factory is not None:
        return server_factory()
    tls = Tls(
        validate=ssl.CERT_REQUIRED,
        ca_certs_file=s.ldap_ca_file,
        version=ssl.PROTOCOL_TLS_CLIENT,
    )
    return Server(s.ldap_url, use_ssl=s.ldap_url.startswith("ldaps://"), tls=tls,
                  connect_timeout=s.ldap_timeout_seconds)  # fmt: skip


def _connect(s: Settings, user: str | None, password: str | None) -> Connection:
    conn = Connection(
        _server(s), user=user, password=password, client_strategy=connection_strategy,
        receive_timeout=s.ldap_timeout_seconds, raise_exceptions=False,
    )  # fmt: skip
    if (
        server_factory is None
        and s.ldap_start_tls
        and not s.ldap_url.startswith("ldaps://")
        and not conn.start_tls()
    ):
        raise LdapUnavailable("StartTLS failed")
    return conn


def _first(entry, attribute: str | None) -> str | None:
    if not attribute or attribute not in entry.entry_attributes:
        return None
    value = entry[attribute].value
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value).strip() or None if value is not None else None


def _find(s: Settings, username: str) -> tuple[str, object | None]:
    """The user's DN (and entry when searched), using the service account or the template."""
    if s.ldap_user_dn_template:
        return s.ldap_user_dn_template.format(username=escape_rdn(username)), None
    conn = _connect(s, s.ldap_bind_dn, s.ldap_bind_password)
    try:
        if not conn.bind():
            raise LdapUnavailable(f"service bind failed: {conn.result.get('description')}")
        query = s.ldap_user_filter.format(username=escape_filter_chars(username))
        conn.search(s.ldap_base_dn, query, SUBTREE, attributes=ALL_ATTRIBUTES, size_limit=2)
        if len(conn.entries) != 1:  # unknown, or ambiguous: refuse
            return "", None
        return conn.entries[0].entry_dn, conn.entries[0]
    finally:
        conn.unbind()


def verify(username: str, password: str) -> DirectoryUser | None:
    """The directory user when the credentials are right, None when they are wrong."""
    s = get_settings()
    username = username.strip()
    if not username or not password or len(username) > 100:
        return None
    try:
        dn, entry = _find(s, username)
        if not dn:
            return None
        conn = _connect(s, dn, password)
        try:
            if not conn.bind():
                return None
            if entry is None:
                conn.search(dn, "(objectClass=*)", "BASE", attributes=ALL_ATTRIBUTES)
                entry = conn.entries[0] if conn.entries else None
        finally:
            conn.unbind()
    except LDAPException as exc:
        raise LdapUnavailable(str(exc)) from exc
    groups = []
    if entry is not None and "memberOf" in entry.entry_attributes:
        groups = [str(g) for g in entry["memberOf"].values]
    return DirectoryUser(
        dn=dn,
        username=username.lower(),
        email=_first(entry, s.ldap_email_attribute) if entry is not None else None,
        full_name=_first(entry, s.ldap_name_attribute) if entry is not None else None,
        student_id=_first(entry, s.ldap_student_id_attribute) if entry is not None else None,
        groups=groups,
    )


def _role(s: Settings, groups: list[str]) -> Role:
    wanted = {g.lower() for g in s.ldap_faculty_groups}
    for group in groups:
        cn = group.split(",")[0].removeprefix("CN=").removeprefix("cn=").lower()
        if group.lower() in wanted or cn in wanted:
            return Role.faculty
    return Role.student


def _free_username(db: Session, wanted: str) -> str:
    candidate, number = wanted[:90], 1
    while db.scalar(select(User.id).where(User.username == candidate)) is not None:
        number += 1
        candidate = f"{wanted[:90]}{number}"
    return candidate


def account(db: Session, directory: DirectoryUser) -> User | None:
    """The local account for a directory user: linked, created, or refreshed."""
    from app.services.auth_service import hash_password

    s = get_settings()
    external_id = f"ldap|{directory.dn}"[:300]
    user = db.scalar(select(User).where(User.external_id == external_id))
    email = (directory.email or f"{directory.username}@ldap.invalid").lower()
    if user is None and directory.email:
        # Link by the directory's e-mail only (never by a username someone could squat).
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and user.external_id is not None:
            return None  # that account belongs to another SSO identity: refuse to merge
    if user is None:
        user = User(
            username=_free_username(db, directory.username),
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),  # directory only
            full_name=(directory.full_name or directory.username)[:255],
            role=_role(s, directory.groups),
            student_id=directory.student_id,
        )
        db.add(user)
    elif user.role is not Role.admin:
        # Group membership can change (a teaching assistant becomes faculty).
        user.role = _role(s, directory.groups)
    user.external_id = external_id
    if directory.full_name:
        user.full_name = directory.full_name[:255]
    db.commit()
    return user
