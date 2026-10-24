"""Simulated login (docs/SPEC.md section 6.2, explicitly allowed by the brief).

There are no passwords. A role switcher writes a signed cookie naming the tenant,
the user and the role. The signature is a stdlib HMAC, so this needs no extra
dependency, and every response that depends on it is labelled `simulated_login`.

A real deployment would replace this module with the Orbyte hub's own session and
take roles from `OrbyteConnector.list_users`.
"""

import base64
import hmac
import hashlib
import json

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import ROLE_OWNER, User

COOKIE_NAME = "orbit_session"
SIMULATED = True


class Principal(BaseModel):
    """Who is making the current request."""

    tenant_id: int
    user_id: int
    role: str
    name: str
    approval_limit_sen: int = 0
    simulated_login: bool = SIMULATED


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    secret = get_settings().session_secret.encode()
    signature = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def unsign(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    secret = get_settings().session_secret.encode()
    expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        return json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None


def set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        sign({"tenant_id": user.tenant_id, "user_id": user.id, "role": user.role}),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )


def _principal_from_user(user: User) -> Principal:
    return Principal(
        tenant_id=user.tenant_id,
        user_id=user.id,
        role=user.role,
        name=user.name,
        approval_limit_sen=user.approval_limit_sen,
    )


def current_principal(
    request: Request,
    session: Session = Depends(get_session),
) -> Principal:
    """Resolve the caller.

    With no cookie, demo mode falls back to the first Owner in the database so a
    fresh checkout is usable immediately. Outside demo mode, no cookie is a 401.
    """
    token = request.cookies.get(COOKIE_NAME)
    claims = unsign(token) if token else None

    if claims:
        user = session.get(User, claims.get("user_id"))
        if user and user.tenant_id == claims.get("tenant_id") and user.role == claims.get("role"):
            return _principal_from_user(user)

    if not get_settings().demo_mode:
        raise HTTPException(status_code=401, detail="Not signed in.")

    user = session.execute(
        select(User).where(User.role == ROLE_OWNER).order_by(User.id).limit(1)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=503,
            detail="No users yet. Run the seed script: python -m seed.generate_data",
        )
    return _principal_from_user(user)
