"""The audit chain must break when anybody edits it (docs/SPEC.md section 14 step 3).

Tampering is done with raw SQL on purpose: the ORM has no update or delete path for
`audit_log`, so raw SQL is the only way a row could realistically be altered, and it
is exactly the attack the chain exists to detect.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import ACTOR_USER, AuditLog, Tenant
from app.services.audit import GENESIS, verify_chain, write_audit


def _write_three(session: Session, tenant_id: int) -> list[AuditLog]:
    """Three audit rows for one tenant, committed."""
    rows = [
        write_audit(
            session,
            tenant_id=tenant_id,
            actor_type=ACTOR_USER,
            actor_id=1,
            action=action,
            entity_type="invoice",
            entity_id=7,
            after={"step": n},
        )
        for n, action in enumerate(("INVOICE_CREATED", "PAYMENT_RECORDED", "INVOICE_PAID"))
    ]
    session.commit()
    return rows


def test_three_writes_chain_from_genesis(session: Session, tenants: tuple[Tenant, Tenant]) -> None:
    a, _ = tenants
    first, second, third = _write_three(session, a.id)

    assert first.hash_prev == GENESIS
    assert second.hash_prev == first.hash_self
    assert third.hash_prev == second.hash_self


def test_verify_chain_reports_ok(session: Session, tenants: tuple[Tenant, Tenant]) -> None:
    a, _ = tenants
    _write_three(session, a.id)

    result = verify_chain(session, a.id)
    assert result["ok"] is True
    assert result["rows_checked"] == 3
    assert result["first_bad_id"] is None


def test_editing_after_json_breaks_verification(
    session: Session, tenants: tuple[Tenant, Tenant]
) -> None:
    a, _ = tenants
    _, middle, _ = _write_three(session, a.id)

    session.execute(
        text("UPDATE audit_log SET after_json = :v WHERE id = :id"),
        {"v": '{"step":999}', "id": middle.id},
    )
    session.commit()
    session.expire_all()

    result = verify_chain(session, a.id)
    assert result["ok"] is False
    assert result["first_bad_id"] == middle.id


def test_editing_action_breaks_verification(
    session: Session, tenants: tuple[Tenant, Tenant]
) -> None:
    a, _ = tenants
    _, middle, _ = _write_three(session, a.id)

    session.execute(
        text("UPDATE audit_log SET action = 'NOTHING_HAPPENED' WHERE id = :id"),
        {"id": middle.id},
    )
    session.commit()
    session.expire_all()

    result = verify_chain(session, a.id)
    assert result["ok"] is False
    assert result["first_bad_id"] == middle.id


def test_deleting_a_row_breaks_the_link(session: Session, tenants: tuple[Tenant, Tenant]) -> None:
    a, _ = tenants
    _, middle, third = _write_three(session, a.id)

    session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": middle.id})
    session.commit()
    session.expire_all()

    # The row left behind now points at a predecessor that is no longer there.
    result = verify_chain(session, a.id)
    assert result["ok"] is False
    assert result["rows_checked"] == 2
    assert result["first_bad_id"] == third.id


def test_tenant_chains_are_independent(session: Session, tenants: tuple[Tenant, Tenant]) -> None:
    a, b = tenants
    _write_three(session, a.id)

    b_first = write_audit(
        session,
        tenant_id=b.id,
        actor_type=ACTOR_USER,
        action="INVOICE_CREATED",
        entity_type="invoice",
        entity_id=1,
    )
    session.commit()

    # Tenant B starts its own chain at genesis and does not disturb tenant A's.
    assert b_first.hash_prev == GENESIS
    assert verify_chain(session, a.id)["rows_checked"] == 3
    assert verify_chain(session, a.id)["ok"] is True
    assert verify_chain(session, b.id)["ok"] is True
