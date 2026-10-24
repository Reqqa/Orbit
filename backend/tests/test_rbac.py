"""Who may approve, and that every refusal is logged (docs/SPEC.md section 14.3)."""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import APPROVE_MATCH, can_approve, deny, require
from app.auth.session import Principal
from app.models import ROLE_FINANCE, ROLE_OWNER, ROLE_SALES, AuditLog, Tenant
from app.money import to_sen
from app.schemas import THRESHOLD_STRONG

LIMIT = to_sen("2000")  # RM 2,000 Finance approval limit
SMALL = to_sen("500")
LARGE = to_sen("3000")
STRONG = THRESHOLD_STRONG
WEAK = THRESHOLD_STRONG - 10

# (label, amount_sen, confidence, is_exception, finance_allowed)
CASES = [
    ("within limit, strong match", SMALL, STRONG, False, True),
    ("above limit", LARGE, STRONG, False, False),
    ("exception, small amount", SMALL, STRONG, True, False),
    ("below strong threshold", SMALL, WEAK, False, False),
]


def _principal(role: str, tenant_id: int) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        user_id=42,
        role=role,
        name=f"Test {role}",
        approval_limit_sen=LIMIT,
    )


@pytest.mark.parametrize("label,amount,confidence,is_exception,finance_allowed", CASES)
def test_finance_limits(
    label: str, amount: int, confidence: int, is_exception: bool, finance_allowed: bool
) -> None:
    allowed, reason = can_approve(
        ROLE_FINANCE,
        amount_sen=amount,
        confidence=confidence,
        is_exception=is_exception,
        approval_limit_sen=LIMIT,
    )
    assert allowed is finance_allowed, f"{label}: {reason}"


@pytest.mark.parametrize("label,amount,confidence,is_exception,finance_allowed", CASES)
def test_owner_may_approve_anything(
    label: str, amount: int, confidence: int, is_exception: bool, finance_allowed: bool
) -> None:
    allowed, _ = can_approve(
        ROLE_OWNER,
        amount_sen=amount,
        confidence=confidence,
        is_exception=is_exception,
        approval_limit_sen=0,  # the Owner's limit is irrelevant
    )
    assert allowed is True, label


def test_sales_is_refused_outright() -> None:
    allowed, reason = can_approve(
        ROLE_SALES,
        amount_sen=to_sen("1"),
        confidence=100,
        is_exception=False,
        approval_limit_sen=LIMIT,
    )
    assert allowed is False
    assert ROLE_SALES in reason


def test_deny_logs_the_refusal_and_returns_403(
    session: Session, tenants: tuple[Tenant, Tenant]
) -> None:
    a, _ = tenants
    principal = _principal(ROLE_SALES, a.id)

    error = deny(
        session,
        principal,
        action="PERMISSION_DENIED",
        entity_type="permission",
        entity_id=APPROVE_MATCH,
        reason="You don't have permission to do this (approve_match).",
    )

    assert isinstance(error, HTTPException)
    assert error.status_code == 403

    row = session.execute(select(AuditLog).where(AuditLog.tenant_id == a.id)).scalar_one()
    assert row.action == "PERMISSION_DENIED"
    after = json.loads(row.after_json)
    assert after["reason"] == "You don't have permission to do this (approve_match)."
    assert after["allowed"] is False
    assert after["role"] == ROLE_SALES


def test_require_refuses_sales_and_logs_it(
    session: Session, tenants: tuple[Tenant, Tenant]
) -> None:
    a, _ = tenants
    dependency = require(APPROVE_MATCH)

    with pytest.raises(HTTPException) as caught:
        dependency(principal=_principal(ROLE_SALES, a.id), session=session)
    assert caught.value.status_code == 403

    row = session.execute(select(AuditLog).where(AuditLog.tenant_id == a.id)).scalar_one()
    assert row.action == "PERMISSION_DENIED"
    assert row.entity_id == APPROVE_MATCH
    assert json.loads(row.after_json)["allowed"] is False


def test_require_lets_finance_through(session: Session, tenants: tuple[Tenant, Tenant]) -> None:
    a, _ = tenants
    principal = require(APPROVE_MATCH)(principal=_principal(ROLE_FINANCE, a.id), session=session)

    assert principal.role == ROLE_FINANCE
    assert session.execute(select(AuditLog)).scalars().all() == []
