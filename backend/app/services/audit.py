"""Append-only, hash-chained audit log (docs/SPEC.md section 8).

Every row stores the hash of the previous row for the same tenant, so editing or
deleting any row breaks verification from that point on. There is deliberately no
update or delete path.

`write_audit` never commits. It flushes into the caller's transaction so the audit
row and the change it records succeed or fail together (CLAUDE.md rule 3).
"""

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, utcnow

GENESIS = "0" * 64


def canonical(payload: Any) -> str | None:
    """Deterministic JSON text. The hash is only reproducible if this never changes."""
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def row_hash(
    *,
    hash_prev: str,
    tenant_id: int,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before_json: str | None,
    after_json: str | None,
    created_at: Any,
) -> str:
    """Hash of one audit row, chained to its predecessor."""
    parts = [
        hash_prev,
        str(tenant_id),
        actor_type,
        actor_id or "",
        action,
        entity_type,
        entity_id or "",
        before_json or "",
        after_json or "",
        created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _last_hash(session: Session, tenant_id: int) -> str:
    stmt = (
        select(AuditLog.hash_self)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar() or GENESIS


def write_audit(
    session: Session,
    *,
    tenant_id: int,
    actor_type: str,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    actor_id: str | int | None = None,
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    """Append one audit row inside the caller's transaction. Does not commit."""
    created_at = utcnow()
    before_json = canonical(before)
    after_json = canonical(after)
    hash_prev = _last_hash(session, tenant_id)
    actor = None if actor_id is None else str(actor_id)
    entity = None if entity_id is None else str(entity_id)

    entry = AuditLog(
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity,
        before_json=before_json,
        after_json=after_json,
        created_at=created_at,
        hash_prev=hash_prev,
        hash_self=row_hash(
            hash_prev=hash_prev,
            tenant_id=tenant_id,
            actor_type=actor_type,
            actor_id=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity,
            before_json=before_json,
            after_json=after_json,
            created_at=created_at,
        ),
    )
    session.add(entry)
    session.flush()
    return entry


def verify_chain(session: Session, tenant_id: int) -> dict[str, Any]:
    """Recompute every hash for a tenant and report the first row that does not match."""
    rows = session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id)
    ).scalars().all()

    expected_prev = GENESIS
    for row in rows:
        if row.hash_prev != expected_prev:
            return _bad(len(rows), row.id, "chain broken: hash_prev does not match the previous row")
        recomputed = row_hash(
            hash_prev=row.hash_prev,
            tenant_id=row.tenant_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            before_json=row.before_json,
            after_json=row.after_json,
            created_at=row.created_at,
        )
        if recomputed != row.hash_self:
            return _bad(len(rows), row.id, "row contents do not match the stored hash")
        expected_prev = row.hash_self

    return {"ok": True, "rows_checked": len(rows), "first_bad_id": None, "detail": "chain intact"}


def _bad(rows_checked: int, row_id: int, detail: str) -> dict[str, Any]:
    return {"ok": False, "rows_checked": rows_checked, "first_bad_id": row_id, "detail": detail}


def export_jsonl(session: Session, tenant_id: int) -> str:
    """The whole chain as JSON Lines, so anyone can re-verify it independently."""
    rows = session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id)
    ).scalars().all()
    lines = []
    for row in rows:
        lines.append(
            json.dumps(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "actor_type": row.actor_type,
                    "actor_id": row.actor_id,
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "before_json": row.before_json,
                    "after_json": row.after_json,
                    "created_at": row.created_at.isoformat(),
                    "hash_prev": row.hash_prev,
                    "hash_self": row.hash_self,
                },
                separators=(",", ":"),
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")
