import logging

from fastapi import APIRouter, Cookie, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import get_settings
from app.routes.deps import DbSession
from app.schemas.auth import TokenPair
from app.services import auth_service, oidc

router = APIRouter(prefix="/api/v1/auth/oidc", tags=["single sign-on"])
log = logging.getLogger(__name__)


class OidcInfo(BaseModel):
    enabled: bool
    name: str


class HandoffRequest(BaseModel):
    handoff: str


def _frontend(fragment: str) -> RedirectResponse:
    url = f"{get_settings().public_url.rstrip('/')}/login#{fragment}"
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(oidc.STATE_COOKIE, path="/")
    return response


def _require_enabled() -> None:
    if not oidc.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Single sign-on is not configured")


@router.get("", response_model=OidcInfo)
def info():
    """Whether the login page shows the university sign-in button."""
    return OidcInfo(enabled=oidc.enabled(), name=get_settings().oidc_display_name)


@router.get("/login")
def login():
    _require_enabled()
    try:
        url, cookie = oidc.start_login()
    except oidc.OidcError as exc:
        log.warning("SSO login could not start: %s", exc)
        return _frontend(f"oidc_error={exc.code}")
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        oidc.STATE_COOKIE,
        cookie,
        max_age=oidc.STATE_MINUTES * 60,
        httponly=True,
        secure=get_settings().public_url.startswith("https://"),
        samesite="lax",  # sent on the provider's top-level redirect back to us
        path="/",
    )
    return response


@router.get("/callback")
def callback(
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    aipe_oidc: str | None = Cookie(default=None),
):
    _require_enabled()
    if error or not code or not state:
        return _frontend("oidc_error=cancelled")
    try:
        user = oidc.finish_login(db, code, state, aipe_oidc)
    except oidc.OidcError as exc:
        log.warning("SSO login failed (%s): %s", exc.code, exc)
        return _frontend(f"oidc_error={exc.code}")
    return _frontend(f"oidc={oidc.handoff_token(user)}")


@router.post("/exchange", response_model=TokenPair)
def exchange(data: HandoffRequest, db: DbSession):
    """One-time handoff from the callback -> the usual access/refresh pair."""
    _require_enabled()
    try:
        user = oidc.redeem_handoff(db, data.handoff)
    except oidc.OidcError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in link expired") from exc
    return auth_service.issue_tokens(user)
