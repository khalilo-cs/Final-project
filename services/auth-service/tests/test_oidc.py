import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings
from app.services import oidc
from tests.test_auth import bearer, login, register

ISSUER = "https://login.university.example/tenant/v2.0"
CLIENT = "aipe-client"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1",
              "use": "sig", "alg": "RS256"}  # fmt: skip


class FakeProvider:
    """A minimal OpenID provider: discovery, JWKS and a PKCE-checking token endpoint."""

    def __init__(self):
        self.claims = {"sub": "u-123", "email": "Sara@University.Example", "email_verified": True,
                       "name": "سارة علي"}  # fmt: skip
        self.pending = {}  # code -> (nonce, code_challenge)
        self.audience = CLIENT
        self.nonce_override = None

    def authorize(self, url: str) -> str:
        """The user signs in at the provider; returns the provider's redirect back."""
        query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert query["client_id"] == CLIENT and query["code_challenge_method"] == "S256"
        self.pending["the-code"] = (query["nonce"], query["code_challenge"])
        return f"/api/v1/auth/oidc/callback?code=the-code&state={query['state']}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/keys",
            })  # fmt: skip
        if request.url.path.endswith("/keys"):
            return httpx.Response(200, json={"keys": [PUBLIC_JWK]})
        if request.url.path.endswith("/token"):
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            nonce, challenge = self.pending.pop(form["code"], (None, None))
            digest = hashlib.sha256(form["code_verifier"].encode()).digest()
            if nonce is None or base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != challenge:
                return httpx.Response(400, json={"error": "invalid_grant"})
            assert form["client_secret"] == "s3cret"
            now = int(time.time())
            token = jwt.encode(
                {**self.claims, "iss": ISSUER, "aud": self.audience, "iat": now,
                 "exp": now + 300, "nonce": self.nonce_override or nonce},
                KEY, algorithm="RS256", headers={"kid": "k1"},
            )  # fmt: skip
            return httpx.Response(200, json={"id_token": token, "access_token": "x"})
        return httpx.Response(404)


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", CLIENT)
    monkeypatch.setattr(settings, "oidc_client_secret", "s3cret")
    monkeypatch.setattr(settings, "public_url", "https://examiner.university.example")
    monkeypatch.setattr(oidc, "transport", httpx.MockTransport(fake))
    oidc._cache.clear()
    return fake


def sign_in(client, provider):
    """Browser walk-through; returns the final redirect's fragment as a dict."""
    client.base_url = "https://testserver"  # the state cookie is Secure on an https site
    start = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert start.status_code == 303
    assert "httponly" in start.headers["set-cookie"].lower()
    back = client.get(provider.authorize(start.headers["location"]), follow_redirects=False)
    assert back.headers["location"].startswith("https://examiner.university.example/login#")
    return dict(parse_qs(urlparse(back.headers["location"]).fragment)), back


def exchange(client, handoff):
    return client.post("/api/v1/auth/oidc/exchange", json={"handoff": handoff})


def test_disabled_by_default(client):
    assert client.get("/api/v1/auth/oidc").json()["enabled"] is False
    assert client.get("/api/v1/auth/oidc/login", follow_redirects=False).status_code == 404


def test_first_sign_in_creates_a_student(client, provider):
    assert client.get("/api/v1/auth/oidc").json() == {"enabled": True, "name": "حساب الجامعة"}
    fragment, _ = sign_in(client, provider)
    tokens = exchange(client, fragment["oidc"][0])
    assert tokens.status_code == 200
    me = client.get("/api/v1/auth/me", headers=bearer(tokens.json()["access_token"])).json()
    assert (me["email"], me["username"], me["role"], me["full_name"]) == (
        "sara@university.example", "sara", "student", "سارة علي",
    )  # fmt: skip
    # The handoff works once only.
    assert exchange(client, fragment["oidc"][0]).status_code == 401

    # Second sign-in: same account (matched by the provider's subject).
    again, _ = sign_in(client, provider)
    me2 = client.get(
        "/api/v1/auth/me", headers=bearer(exchange(client, again["oidc"][0]).json()["access_token"])
    ).json()
    assert me2["id"] == me["id"]


def test_existing_account_is_linked_and_password_still_works(client, provider):
    register(client, email="sara@university.example", username="sara.a")
    fragment, _ = sign_in(client, provider)
    me = client.get(
        "/api/v1/auth/me",
        headers=bearer(exchange(client, fragment["oidc"][0]).json()["access_token"]),
    ).json()
    assert me["username"] == "sara.a"
    assert login(client, "sara.a").status_code == 200


def test_faculty_role_from_claim_never_admin(client, provider, monkeypatch):
    monkeypatch.setattr(get_settings(), "oidc_role_claim", "roles")
    monkeypatch.setattr(get_settings(), "oidc_faculty_values", ["Faculty", "admin"])
    provider.claims["roles"] = ["Faculty"]
    fragment, _ = sign_in(client, provider)
    token = exchange(client, fragment["oidc"][0]).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=bearer(token)).json()["role"] == "faculty"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda p, s: setattr(p, "audience", "someone-else"), "invalid_token"),
        (lambda p, s: setattr(p, "nonce_override", "replayed"), "invalid_token"),
        (lambda p, s: p.claims.update(email_verified=False), "email_not_verified"),
        (lambda p, s: p.claims.pop("email_verified"), "email_not_verified"),
        (lambda p, s: setattr(s, "oidc_allowed_domains", ["su.edu.ye"]), "domain_not_allowed"),
    ],
)
def test_rejected_sign_ins(client, provider, monkeypatch, change, code):
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_allowed_domains", [])
    change(provider, settings)
    fragment, _ = sign_in(client, provider)
    assert fragment == {"oidc_error": [code]}


def test_unverified_email_accepted_for_the_universitys_own_domain(client, provider, monkeypatch):
    # e.g. Microsoft Entra sends no email_verified; the tenant is authoritative for its domain.
    monkeypatch.setattr(get_settings(), "oidc_allowed_domains", ["university.example"])
    provider.claims.pop("email_verified")
    fragment, _ = sign_in(client, provider)
    assert "oidc" in fragment


def test_state_must_match_the_browsers_cookie(client, provider):
    client.base_url = "https://testserver"
    start = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    callback = provider.authorize(start.headers["location"]).replace("state=", "state=x")
    back = client.get(callback, follow_redirects=False)
    assert back.headers["location"].endswith("#oidc_error=expired")
    client.cookies.clear()  # another browser: no cookie at all
    back = client.get(provider.authorize(start.headers["location"]), follow_redirects=False)
    assert back.headers["location"].endswith("#oidc_error=expired")
    assert client.get("/api/v1/auth/oidc/callback?error=access_denied",
                      follow_redirects=False).headers["location"].endswith("cancelled")  # fmt: skip


def test_provider_down(client, provider, monkeypatch):
    monkeypatch.setattr(oidc, "transport", httpx.MockTransport(lambda r: httpx.Response(503)))
    oidc._cache.clear()
    back = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert back.headers["location"].endswith("#oidc_error=provider_unreachable")
