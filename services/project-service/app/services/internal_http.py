"""Calls from project-service to the other services, with a short-lived service token."""

import logging
import time
import uuid

import httpx
import jwt

from app.config import get_settings

log = logging.getLogger(__name__)

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


def service_token() -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "role": "service",
        "type": "access",
        "iat": now,
        "exp": now + 600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def client(base_url: str, timeout: float) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        transport=transport,
        headers={"Authorization": f"Bearer {service_token()}"},
    )


def lookup_users(ids: set[uuid.UUID]) -> dict[str, dict]:
    """id -> {full_name, username, student_id}. Empty when auth-service is unreachable."""
    if not ids:
        return {}
    try:
        with client(get_settings().auth_service_url, timeout=10) as http:
            response = http.post(
                "/api/v1/internal/users/lookup", json={"ids": [str(i) for i in ids]}
            )
            response.raise_for_status()
            return {user["id"]: user for user in response.json()}
    except (httpx.HTTPError, ValueError):
        log.warning("user lookup failed; names will be missing")
        return {}
