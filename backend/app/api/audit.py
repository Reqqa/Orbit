"""The audit log: read it, verify it, export it (docs/SPEC.md sections 8 and 9.6).

There is no endpoint that changes or deletes an audit row, by design.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import VIEW_AUDIT, require
from app.auth.session import Principal
from app.db import get_session
from app.models import ACTOR_AI, ACTOR_USER, AuditLog, User
from app.services.audit import export_jsonl, verify_chain

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    action: str | None = None,
    actor_type: str | None = None,
    limit: int = 200,
    principal: Principal = Depends(require(VIEW_AUDIT)),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Newest first, filterable by action or actor type."""
    stmt = select(AuditLog).where(AuditLog.tenant_id == principal.tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action.upper())
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type.upper())

    rows = session.execute(stmt.order_by(AuditLog.id.desc()).limit(min(limit, 1000))).scalars()
    return [_serialise(session, row) for row in rows]


@router.get("/verify")
def verify(
    principal: Principal = Depends(require(VIEW_AUDIT)),
    session: Session = Depends(get_session),
) -> dict:
    """Recompute the whole hash chain for this tenant."""
    result = verify_chain(session, principal.tenant_id)
    return {
        **result,
        "tenant_id": principal.tenant_id,
        "how_to_check_yourself": (
            "Export the log and re-hash each row as "
            "sha256(hash_prev|tenant_id|actor_type|actor_id|action|entity_type|"
            "entity_id|before_json|after_json|created_at)."
        ),
    }


@router.get("/export.jsonl")
def export(
    principal: Principal = Depends(require(VIEW_AUDIT)),
    session: Session = Depends(get_session),
) -> Response:
    """The chain as JSON Lines so a judge can verify it independently."""
    body = export_jsonl(session, principal.tenant_id)
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="orbit-audit-tenant{principal.tenant_id}.jsonl"'
        },
    )


def _serialise(session: Session, row: AuditLog) -> dict:
    actor_name = None
    if row.actor_type == ACTOR_USER and row.actor_id and str(row.actor_id).isdigit():
        user = session.get(User, int(row.actor_id))
        actor_name = user.name if user else None
    elif row.actor_type == ACTOR_AI:
        actor_name = row.actor_id  # the model name

    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "actor_name": actor_name,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "before": row.before_json,
        "after": row.after_json,
        "hash_self": row.hash_self,
        "hash_prev": row.hash_prev,
    }
