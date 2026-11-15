"""Sign in with the university's identity provider (OpenID Connect, code flow + PKCE).

1. /oidc/login: a random state, nonce and PKCE verifier go into a short-lived signed
   cookie, and the browser is sent to the provider.
2. /oidc/callback: state is checked against the cookie, the code is exchanged for an
   ID token, whose signature (provider JWKS), issuer, audience, expiry and nonce are
   verified. The account is found or created.
3. The browser gets a one-time, 60-second handoff token in the URL fragment (never sent
   to a server or written to logs) and exchanges it for the usual token pair.
"""

import base64
import hashlib
import re
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.user import RevokedToken, Role, User
from app.services.auth_service import hash_password

STATE_COOKIE = "aipe_oidc"
STATE_MINUTES = 10
HANDOFF_SECONDS = 60
_SIGNING_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]
_DISCOVERY_TTL = 3600
_cache: dict[str, tuple[float, dict]] = {}
# Tests replace this with httpx.MockTransport.
transport: httpx.BaseTransport | None = None


class OidcError(Exception):
    """`code` is shown to the user as a short Arabic message by the web interface."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.oidc_issuer and s.oidc_client_id and s.oidc_client_secret)


def redirect_uri(settings: Settings) -> str:
    return settings.oidc_redirect_uri or (
        f"{settings.public_url.rstrip('/')}/svc/auth/api/v1/auth/oidc/callback"
    )


def _http() -> httpx.Client:
    return httpx.Client(timeout=15, transport=transport)


def _cached(url: str) -> dict:
    hit = _cache.get(url)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        with _http() as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("provider_unreachable", f"{url}: {exc}") from exc
    _cache[url] = (time.monotonic() + _DISCOVERY_TTL, data)
    return data


def metadata(settings: Settings) -> dict:
    issuer = (settings.oidc_issuer or "").rstrip("/")
    data = _cached(f"{issuer}/.well-known/openid-configuration")
    if data.get("issuer", "").rstrip("/") != issuer:
        raise OidcError("provider_misconfigured", "issuer in discovery document differs")
    return data


def _sign(claims: dict, minutes: float) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def _verify_own(token: str, kind: str) -> dict:
    s = get_settings()
    try:
        claims = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm],
                            options={"require": ["exp", "type"]})  # fmt: skip
    except jwt.PyJWTError as exc:
        raise OidcError("expired", str(exc)) from exc
    if claims["type"] != kind:
        raise OidcError("expired", "wrong token type")
    return claims


def start_login() -> tuple[str, str]:
    """(provider URL to redirect to, signed state cookie)."""
    s = get_settings()
    meta = metadata(s)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    query = urlencode({
        "response_type": "code",
        "client_id": s.oidc_client_id,
        "redirect_uri": redirect_uri(s),
        "scope": s.oidc_scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge.rstrip(b"=").decode(),
        "code_challenge_method": "S256",
    })  # fmt: skip
    cookie = _sign({"type": "oidc_state", "state": state, "nonce": nonce, "verifier": verifier},
                   STATE_MINUTES)  # fmt: skip
    return f"{meta['authorization_endpoint']}?{query}", cookie


def _exchange_code(s: Settings, meta: dict, code: str, verifier: str) -> str:
    try:
        with _http() as client:
            response = client.post(
                meta["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri(s),
                    "client_id": s.oidc_client_id,
                    "client_secret": s.oidc_client_secret,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            id_token = response.json().get("id_token")
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("token_exchange_failed", str(exc)) from exc
    if not id_token:
        raise OidcError("token_exchange_failed", "no id_token in the response")
    return id_token


def _verify_id_token(s: Settings, meta: dict, id_token: str, nonce: str) -> dict:
    try:
        kid = jwt.get_unverified_header(id_token).get("kid")
        keys = jwt.PyJWKSet.from_dict(_cached(meta["jwks_uri"])).keys
        key = next((k for k in keys if kid is None or k.key_id == kid), None)
        if key is None:  # provider rotated its keys: refresh once
            _cache.pop(meta["jwks_uri"], None)
            keys = jwt.PyJWKSet.from_dict(_cached(meta["jwks_uri"])).keys
            key = next(k for k in keys if kid is None or k.key_id == kid)
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=_SIGNING_ALGORITHMS,
            audience=s.oidc_client_id,
            issuer=meta["issuer"],
            leeway=60,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except (jwt.PyJWTError, StopIteration, KeyError) as exc:
        raise OidcError("invalid_token", str(exc)) from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OidcError("invalid_token", "nonce mismatch")
    return claims


def _email(s: Settings, claims: dict) -> str:
    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if "@" not in email:
        raise OidcError("no_email", "the provider sent no e-mail address")
    domain = email.rsplit("@", 1)[1]
    allowed = [d.lower().lstrip("@") for d in s.oidc_allowed_domains]
    if allowed and domain not in allowed:
        raise OidcError("domain_not_allowed", domain)
    # An address is trusted when the provider verified it, or when it belongs to a
    # domain this provider is configured as the authority for.
    if claims.get("email_verified") is not True and not allowed:
        raise OidcError("email_not_verified", email)
    if claims.get("email_verified") is False:
        raise OidcError("email_not_verified", email)
    return email


def _role(s: Settings, claims: dict) -> Role:
    if not s.oidc_role_claim:
        return Role.student
    values = claims.get(s.oidc_role_claim) or []
    values = [values] if isinstance(values, str) else values
    wanted = {v.lower() for v in s.oidc_faculty_values}
    return Role.faculty if any(str(v).lower() in wanted for v in values) else Role.student


def _username(db: Session, claims: dict, email: str) -> str:
    base = re.sub(r"[^a-z0-9_.-]", "", email.split("@")[0].lower())[:90] or "user"
    candidate, n = base, 1
    while db.scalar(select(User.id).where(User.username == candidate)) is not None:
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _account(db: Session, s: Settings, claims: dict) -> User:
    external_id = f"{claims['iss']}|{claims['sub']}"[:300]
    user = db.scalar(select(User).where(User.external_id == external_id))
    if user is not None:
        return user
    email = _email(s, claims)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        if user.external_id is not None:  # linked to another SSO identity already
            raise OidcError("account_conflict", email)
        user.external_id = external_id  # first SSO sign-in of an existing account
        db.commit()
        return user
    student_id = claims.get(s.oidc_student_id_claim) if s.oidc_student_id_claim else None
    user = User(
        username=_username(db, claims, email),
        email=email,
        # Unusable password: this account signs in through the university only.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        full_name=(claims.get("name") or email.split("@")[0])[:255],
        role=_role(s, claims),
        student_id=str(student_id)[:50] if student_id else None,
        external_id=external_id,
    )
    db.add(user)
    db.commit()
    return user


def finish_login(db: Session, code: str, state: str, cookie: str | None) -> User:
    if not cookie:
        raise OidcError("expired", "state cookie missing")
    saved = _verify_own(cookie, "oidc_state")
    if not secrets.compare_digest(saved["state"], state):
        raise OidcError("expired", "state mismatch")
    s = get_settings()
    meta = metadata(s)
    id_token = _exchange_code(s, meta, code, saved["verifier"])
    claims = _verify_id_token(s, meta, id_token, saved["nonce"])
    return _account(db, s, claims)


def handoff_token(user: User) -> str:
    return _sign({"type": "oidc_handoff", "sub": str(user.id), "jti": str(uuid.uuid4())},
                 HANDOFF_SECONDS / 60)  # fmt: skip


def redeem_handoff(db: Session, token: str) -> User:
    """Each handoff works once."""
    claims = _verify_own(token, "oidc_handoff")
    if db.get(RevokedToken, claims["jti"]) is not None:
        raise OidcError("expired", "handoff already used")
    db.add(RevokedToken(jti=claims["jti"], expires_at=datetime.fromtimestamp(claims["exp"], UTC)))
    db.commit()
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None:
        raise OidcError("expired", "account removed")
    return user
