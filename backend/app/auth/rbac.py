"""Role permissions and approval limits (docs/SPEC.md section 4).

Two rules carry the whole "people stay in control" story:
  1. Only Owner and Finance can approve, and Finance only within their limit,
     only on a strong match, and never on an exception.
  2. Every refusal is written to the audit log before the 403 is raised.
"""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.session import Principal, current_principal
from app.db import get_session
from app.models import ACTOR_USER, ROLE_FINANCE, ROLE_OWNER, ROLE_SALES
from app.schemas import THRESHOLD_STRONG
from app.services.audit import write_audit

# Permission names used by the API layer.
VIEW_ALL = "view_all"
VIEW_OWN_CUSTOMERS = "view_own_customers"
APPROVE_MATCH = "approve_match"
APPROVE_BATCH = "approve_batch"
MANAGE_SETTINGS = "manage_settings"
VIEW_AUDIT = "view_audit"

PERMISSIONS: dict[str, set[str]] = {
    ROLE_OWNER: {VIEW_ALL, VIEW_OWN_CUSTOMERS, APPROVE_MATCH, APPROVE_BATCH, MANAGE_SETTINGS, VIEW_AUDIT},
    ROLE_FINANCE: {VIEW_ALL, VIEW_OWN_CUSTOMERS, APPROVE_MATCH, VIEW_AUDIT},
    ROLE_SALES: {VIEW_OWN_CUSTOMERS},
}


def has_perm(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def can_approve(
    role: str,
    *,
    amount_sen: int,
    confidence: int,
    is_exception: bool,
    approval_limit_sen: int,
) -> tuple[bool, str]:
    """May this role approve this particular item? Returns (allowed, reason)."""
    if role == ROLE_OWNER:
        return True, "Owner may approve anything."
    if not has_perm(role, APPROVE_MATCH):
        return False, f"{role} is not allowed to approve payments."
    if role == ROLE_FINANCE:
        if is_exception:
            return False, "Exceptions must be approved by the Owner."
        if amount_sen > approval_limit_sen:
            return False, "Amount is above your approval limit."
        if confidence < THRESHOLD_STRONG:
            return False, "Confidence is below the strong-match threshold; the Owner must approve."
    return True, "Within your approval limit."


def deny(
    session: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    reason: str,
) -> HTTPException:
    """Log the refusal, commit it, and hand back the 403 for the caller to raise.

    The commit is deliberate: the request is about to fail, and the attempt must
    survive regardless (docs/SPEC.md section 14 step 5).
    """
    write_audit(
        session,
        tenant_id=principal.tenant_id,
        actor_type=ACTOR_USER,
        actor_id=principal.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        after={"role": principal.role, "reason": reason, "allowed": False},
    )
    session.commit()
    return HTTPException(status_code=403, detail=reason)


def require(permission: str):
    """Dependency factory: 403 and an audit row if the role lacks the permission."""

    def dependency(
        principal: Principal = Depends(current_principal),
        session: Session = Depends(get_session),
    ) -> Principal:
        if not has_perm(principal.role, permission):
            raise deny(
                session,
                principal,
                action="PERMISSION_DENIED",
                entity_type="permission",
                entity_id=permission,
                reason=f"You don't have permission to do this ({permission}).",
            )
        return principal

    return dependency
