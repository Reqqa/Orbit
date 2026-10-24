"""Recording a payment against invoices.

Everything here runs inside the caller's transaction. The caller commits once, so
the payment, its allocations, the invoice status changes and the audit rows either
all land or none of them do (docs/SPEC.md section 5.1 step 8).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ACTOR_USER,
    INVOICE_OPEN,
    INVOICE_PAID,
    INVOICE_PARTIAL,
    Invoice,
    MatchProposal,
    Payment,
    PaymentAllocation,
    utcnow,
)
from app.money import fmt_sen
from app.schemas import Allocation
from app.services.audit import write_audit


class LedgerError(RuntimeError):
    """Raised when a payment cannot be recorded as asked."""


def apply_payment(
    session: Session,
    *,
    proposal: MatchProposal,
    decided_by: int,
    amount_sen: int,
    allocations: list[Allocation],
    paid_at: datetime | None = None,
    channel: str | None = None,
    reference: str | None = None,
    transaction_id: str | None = None,
) -> Payment:
    """Create the payment, allocate it, move the invoices. Does not commit."""
    if amount_sen <= 0:
        raise LedgerError("A payment must be for a positive amount.")
    if not allocations:
        raise LedgerError("Choose at least one invoice for this payment.")

    allocated = sum(a.amount_sen for a in allocations)
    if allocated > amount_sen:
        raise LedgerError(
            f"Allocated {fmt_sen(allocated)} but the payment is only {fmt_sen(amount_sen)}."
        )

    # Checked here, at the moment of recording, not only when the receipt arrived:
    # two copies of one receipt can both be waiting, and approving the first must
    # stop the second from recording the same money again.
    if transaction_id:
        already = session.execute(
            select(Payment.id).where(
                Payment.tenant_id == proposal.tenant_id,
                Payment.transaction_id == transaction_id,
            )
        ).scalars().first()
        if already is not None:
            raise LedgerError(
                f"Transaction {transaction_id} is already recorded as payment {already}. "
                "Reject this copy."
            )

    invoices: dict[int, Invoice] = {}
    for allocation in allocations:
        invoice = session.get(Invoice, allocation.invoice_id)
        if invoice is None or invoice.tenant_id != proposal.tenant_id:
            raise LedgerError(f"Invoice {allocation.invoice_id} is not in this business.")
        if allocation.amount_sen <= 0:
            raise LedgerError(f"Allocation for {invoice.invoice_no} must be positive.")
        if allocation.amount_sen > invoice.outstanding_sen:
            raise LedgerError(
                f"{invoice.invoice_no} has only {fmt_sen(invoice.outstanding_sen)} outstanding, "
                f"so {fmt_sen(allocation.amount_sen)} cannot be recorded against it. "
                "It may already have been paid."
            )
        invoices[allocation.invoice_id] = invoice

    payment = Payment(
        tenant_id=proposal.tenant_id,
        customer_id=proposal.customer_id,
        amount_sen=amount_sen,
        paid_at=paid_at or utcnow(),
        channel=channel,
        reference=reference,
        transaction_id=transaction_id,
        proposal_id=proposal.id,
        recorded_by=decided_by,
    )
    session.add(payment)
    session.flush()

    write_audit(
        session,
        tenant_id=proposal.tenant_id,
        actor_type=ACTOR_USER,
        actor_id=decided_by,
        action="PAYMENT_RECORDED",
        entity_type="payment",
        entity_id=payment.id,
        after={
            "amount_sen": amount_sen,
            "customer_id": proposal.customer_id,
            "proposal_id": proposal.id,
            "transaction_id": transaction_id,
            "allocations": [a.model_dump() for a in allocations],
        },
    )

    for allocation in allocations:
        invoice = invoices[allocation.invoice_id]
        before = {"outstanding_sen": invoice.outstanding_sen, "status": invoice.status}

        session.add(
            PaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                amount_sen=allocation.amount_sen,
            )
        )

        invoice.outstanding_sen -= allocation.amount_sen
        if invoice.outstanding_sen == 0:
            invoice.status = INVOICE_PAID
        elif invoice.outstanding_sen < invoice.total_sen:
            invoice.status = INVOICE_PARTIAL
        else:
            invoice.status = INVOICE_OPEN

        write_audit(
            session,
            tenant_id=proposal.tenant_id,
            actor_type=ACTOR_USER,
            actor_id=decided_by,
            action="INVOICE_UPDATED",
            entity_type="invoice",
            entity_id=invoice.id,
            before=before,
            after={"outstanding_sen": invoice.outstanding_sen, "status": invoice.status},
        )

    session.flush()
    return payment


def customer_balance_sen(session: Session, tenant_id: int, customer_id: int) -> int:
    """Total still owed by one customer."""
    from sqlalchemy import func, select

    total = session.execute(
        select(func.coalesce(func.sum(Invoice.outstanding_sen), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.customer_id == customer_id,
            Invoice.status.in_((INVOICE_OPEN, INVOICE_PARTIAL)),
        )
    ).scalar_one()
    return int(total)
