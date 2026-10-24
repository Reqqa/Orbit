"""Who am I, and the demo role switcher (docs/SPEC.md section 9.9)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.session import Principal, current_principal, set_session_cookie
from app.config import get_settings
from app.db import get_session
from app.models import Tenant, User
from app.money import fmt_sen

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/session")
def read_session(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict:
    """The signed-in user, their tenant, and an honest note that login is simulated."""
    tenant = session.get(Tenant, principal.tenant_id)
    return {
        "user_id": principal.user_id,
        "name": principal.name,
        "role": principal.role,
        "approval_limit_sen": principal.approval_limit_sen,
        "approval_limit_display": (
            "No limit" if not principal.approval_limit_sen else fmt_sen(principal.approval_limit_sen)
        ),
        "tenant_id": principal.tenant_id,
        "tenant_name": tenant.name if tenant else None,
        "tenant_whatsapp_number": tenant.whatsapp_number if tenant else None,
        "simulated_login": True,
        "demo_mode": get_settings().demo_mode,
    }


@router.get("/session/users")
def switchable_users(session: Session = Depends(get_session)) -> list[dict]:
    """Everyone the role switcher can become. Demo mode only."""
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404, detail="Not available outside demo mode.")
    rows = session.execute(
        select(User, Tenant).join(Tenant, Tenant.id == User.tenant_id).order_by(User.tenant_id, User.id)
    ).all()
    return [
        {
            "user_id": user.id,
            "name": user.name,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "tenant_name": tenant.name,
            "approval_limit_sen": user.approval_limit_sen,
        }
        for user, tenant in rows
    ]


@router.post("/session")
def switch_user(
    payload: dict,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    """Become another user. This is the simulated login the brief allows."""
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404, detail="Not available outside demo mode.")

    user = session.get(User, int(payload.get("user_id", 0)))
    if user is None:
        raise HTTPException(status_code=404, detail="No such user.")

    set_session_cookie(response, user)
    return {
        "user_id": user.id,
        "name": user.name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "simulated_login": True,
    }
