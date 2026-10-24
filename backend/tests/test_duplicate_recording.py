"""A receipt can be recorded once, however many copies are waiting (docs/SPEC.md section 7.3).

Duplicate classification catches a copy when it arrives, but two copies can both be
waiting before either is approved. These tests are the guard at the moment of
recording, against a real (throwaway) database.
"""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ROLE_OWNER,
    Customer,
    Invoice,
    MatchProposal,
    Payment,
    Tenant,
    User,
    WhatsappMessage,
)
from app.schemas import EXACT_MATCH, Allocation
from app.services.ledger import LedgerError, apply_payment

AMOUNT = 67745  # RM 677.45, the whole outstanding balance


@pytest.fixture
def invoice(session: Session, tenants: tuple[Tenant, Tenant]) -> Invoice:
    tenant, _ = tenants
    customer = Customer(tenant_id=tenant.id, name="Chee Hwa Peng Mini Market", phone_hmac="h", phone_enc="e")
    session.add(customer)
    session.flush()
    inv = Invoice(
        tenant_id=tenant.id,
        customer_id=customer.id,
        invoice_no="INV-1003",
        issue_date=date(2026, 9, 26),
        due_date=date(2026, 10, 26),
        total_sen=118850,
        outstanding_sen=AMOUNT,
        status="PARTIAL",
    )
    owner = User(tenant_id=tenant.id, name="Owner", role=ROLE_OWNER)
    session.add_all([inv, owner])
    session.commit()
    return inv


def _proposal(session: Session, invoice: Invoice, n: int) -> MatchProposal:
    message = WhatsappMessage(tenant_id=invoice.tenant_id, wa_message_id=f"sim-{n}", type="image")
    session.add(message)
    session.flush()
    proposal = MatchProposal(
        tenant_id=invoice.tenant_id,
        message_id=message.id,
        customer_id=invoice.customer_id,
        classification=EXACT_MATCH,
    )
    session.add(proposal)
    session.flush()
    return proposal


def _record(session: Session, invoice: Invoice, proposal: MatchProposal, transaction_id: str | None) -> Payment:
    owner_id = session.execute(select(User.id)).scalar_one()
    return apply_payment(
        session,
        proposal=proposal,
        decided_by=owner_id,
        amount_sen=AMOUNT,
        allocations=[Allocation(invoice_id=invoice.id, invoice_no=invoice.invoice_no, amount_sen=AMOUNT)],
        transaction_id=transaction_id,
    )


def _payments(session: Session) -> int:
    return session.execute(select(func.count(Payment.id))).scalar_one()


def test_the_second_copy_of_a_recorded_transaction_is_refused(session: Session, invoice: Invoice) -> None:
    first, second = _proposal(session, invoice, 1), _proposal(session, invoice, 2)
    _record(session, invoice, first, "TX5692081678")
    session.commit()

    with pytest.raises(LedgerError, match="already recorded"):
        _record(session, invoice, second, "TX5692081678")
    session.rollback()

    assert _payments(session) == 1
    assert session.get(Invoice, invoice.id).outstanding_sen == 0


def test_money_cannot_be_recorded_against_an_invoice_that_is_already_paid(
    session: Session, invoice: Invoice
) -> None:
    # No transaction ID to compare, so the invoice balance is the only guard left.
    first, second = _proposal(session, invoice, 1), _proposal(session, invoice, 2)
    _record(session, invoice, first, None)
    session.commit()

    with pytest.raises(LedgerError, match="only RM 0.00 outstanding"):
        _record(session, invoice, second, None)
    session.rollback()

    assert _payments(session) == 1
    assert session.get(Invoice, invoice.id).status == "PAID"
