"""The approval gate. Nothing consequential happens without passing through here.

Role and amount limit are checked server-side, the refusal is logged, and on
approval the payment, the invoices, the audit rows and the customer's confirmation
all happen in one transaction (docs/SPEC.md sections 4 and 5.1 step 8).
"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.rbac import APPROVE_MATCH, can_approve, deny, has_perm
from app.auth.session import Principal
from app.connectors.orbyte import get_connector
from app.models import (
    ACTOR_SYSTEM,
    ACTOR_USER,
    PROPOSAL_APPROVED,
    PROPOSAL_PENDING,
    PROPOSAL_REJECTED,
    Customer,
    Extraction,
    Invoice,
    MatchProposal,
    utcnow,
)
from app.money import fmt_sen
from app.schemas import (
    EXACT_MATCH,
    EXCEPTION_CLASSIFICATIONS,
    PARTIAL_PAYMENT,
    Allocation,
    ExtractedFields,
)
from app.services.audit import write_audit
from app.services.ledger import LedgerError, apply_payment
from app.services.notify import notify_customer
from app.templates import messages as templates

log = logging.getLogger("orbit.approval")

APPROVE = "approve"
REJECT = "reject"


def decide_proposal(
    session: Session,
    principal: Principal,
    *,
    proposal_id: int,
    decision: str,
    note: str | None = None,
    edits: dict | None = None,
) -> dict:
    """Apply a human decision to one proposal. Commits on success."""
    proposal = session.get(MatchProposal, proposal_id)
    if proposal is None or proposal.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="That approval item does not exist.")
    if proposal.status != PROPOSAL_PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"This item was already {proposal.status.lower()}.",
        )
    if decision not in (APPROVE, REJECT):
        raise HTTPException(status_code=400, detail="Decision must be approve or reject.")

    if not has_perm(principal.role, APPROVE_MATCH):
        raise deny(
            session,
            principal,
            action="APPROVAL_DENIED",
            entity_type="match_proposal",
            entity_id=proposal.id,
            reason="You don't have permission to approve payments.",
        )

    fields = _extracted(session, proposal)
    edits = edits or {}
    amount_sen = int(edits.get("amount_sen") or fields.amount_sen or 0)
    allocations = _allocations(session, proposal, amount_sen, edits)

    allowed, reason = can_approve(
        principal.role,
        amount_sen=amount_sen,
        confidence=proposal.confidence,
        is_exception=proposal.classification in EXCEPTION_CLASSIFICATIONS,
        approval_limit_sen=principal.approval_limit_sen,
    )
    if not allowed:
        raise deny(
            session,
            principal,
            action="APPROVAL_DENIED",
            entity_type="match_proposal",
            entity_id=proposal.id,
            reason=reason,
        )

    if decision == REJECT:
        return _reject(session, principal, proposal, note)

    return _approve(session, principal, proposal, fields, amount_sen, allocations, note, edits)


def _approve(
    session: Session,
    principal: Principal,
    proposal: MatchProposal,
    fields: ExtractedFields,
    amount_sen: int,
    allocations: list[Allocation],
    note: str | None,
    edits: dict,
) -> dict:
    before = {"status": proposal.status}
    try:
        payment = apply_payment(
            session,
            proposal=proposal,
            decided_by=principal.user_id,
            amount_sen=amount_sen,
            allocations=allocations,
            paid_at=fields.transaction_datetime.replace(tzinfo=None)
            if fields.transaction_datetime
            else None,
            channel=fields.channel,
            reference=fields.reference_text,
            transaction_id=fields.transaction_id,
        )
    except LedgerError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    proposal.status = PROPOSAL_APPROVED
    proposal.decided_by = principal.user_id
    proposal.decided_at = utcnow()
    proposal.decision_note = note

    write_audit(
        session,
        tenant_id=proposal.tenant_id,
        actor_type=ACTOR_USER,
        actor_id=principal.user_id,
        action="PROPOSAL_APPROVED",
        entity_type="match_proposal",
        entity_id=proposal.id,
        before=before,
        after={
            "status": proposal.status,
            "payment_id": payment.id,
            "amount_sen": amount_sen,
            "note": note,
            "edits": edits or None,
        },
    )

    # Push the payment and the activity event back to the hub. The mock connector
    # echoes them; a real one would POST to /orbyte/v1/payments and
    # /orbyte/v1/activity-log (docs/SPEC.md section 13). The idempotency key is the
    # proposal, which is unique per payment.
    hub = get_connector(session)
    hub_payment = hub.record_payment(
        proposal.tenant_id,
        {
            "payment_id": payment.id,
            "customer_id": proposal.customer_id,
            "amount_sen": amount_sen,
            "paid_at": payment.paid_at.isoformat(),
            "reference": payment.reference,
            "transaction_id": payment.transaction_id,
            "allocations": [a.model_dump() for a in allocations],
        },
        idempotency_key=f"orbit-proposal-{proposal.id}",
    )
    hub_activity = hub.push_activity(
        proposal.tenant_id,
        {
            "action": "PAYMENT_RECORDED",
            "actor": principal.name,
            "role": principal.role,
            "payment_id": payment.id,
            "amount_sen": amount_sen,
        },
    )
    write_audit(
        session,
        tenant_id=proposal.tenant_id,
        actor_type=ACTOR_SYSTEM,
        action="HUB_SYNCED",
        entity_type="payment",
        entity_id=payment.id,
        after={
            "payment_accepted": bool(hub_payment.get("accepted")),
            "activity_accepted": bool(hub_activity.get("accepted")),
            "simulated": bool(hub_payment.get("simulated")),
            "idempotency_key": f"orbit-proposal-{proposal.id}",
        },
    )

    customer = session.get(Customer, proposal.customer_id) if proposal.customer_id else None
    invoice_no = allocations[0].invoice_no if allocations else ""
    if customer is not None:
        remaining = _remaining_sen(session, allocations)
        template_id = (
            templates.PAYMENT_PARTIAL if remaining > 0 else templates.PAYMENT_CONFIRMED
        )
        notify_customer(
            session,
            tenant_id=proposal.tenant_id,
            customer=customer,
            template_id=template_id,
            customer_name=customer.name,
            amount=fmt_sen(amount_sen),
            invoice_no=invoice_no,
            outstanding=fmt_sen(remaining),
        )

    session.commit()
    log.info("proposal %s approved by %s", proposal.id, principal.name)

    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "payment_id": payment.id,
        "amount_display": fmt_sen(amount_sen),
        "allocations": [a.model_dump() for a in allocations],
        "message": f"Recorded {fmt_sen(amount_sen)} against {invoice_no}.",
    }


def _reject(
    session: Session,
    principal: Principal,
    proposal: MatchProposal,
    note: str | None,
) -> dict:
    before = {"status": proposal.status}
    proposal.status = PROPOSAL_REJECTED
    proposal.decided_by = principal.user_id
    proposal.decided_at = utcnow()
    proposal.decision_note = note

    write_audit(
        session,
        tenant_id=proposal.tenant_id,
        actor_type=ACTOR_USER,
        actor_id=principal.user_id,
        action="PROPOSAL_REJECTED",
        entity_type="match_proposal",
        entity_id=proposal.id,
        before=before,
        after={"status": proposal.status, "note": note},
    )

    customer = session.get(Customer, proposal.customer_id) if proposal.customer_id else None
    if customer is not None:
        notify_customer(
            session,
            tenant_id=proposal.tenant_id,
            customer=customer,
            template_id=templates.NEED_CLARIFICATION,
            customer_name=customer.name,
            amount=fmt_sen(_amount_of(session, proposal)),
            missing=note or "we could not match it to one of your invoices",
        )

    session.commit()
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "message": "Rejected. The customer has been asked to clarify. Nothing was recorded.",
    }


def _amount_of(session: Session, proposal: MatchProposal) -> int:
    """The amount read off the receipt, for use in a message to the customer."""
    extraction = session.get(Extraction, proposal.extraction_id) if proposal.extraction_id else None
    return int((extraction.raw_json or {}).get("amount_sen") or 0) if extraction else 0


def _extracted(session: Session, proposal: MatchProposal) -> ExtractedFields:
    extraction = session.get(Extraction, proposal.extraction_id) if proposal.extraction_id else None
    if extraction is None:
        raise HTTPException(status_code=409, detail="This item has no receipt reading attached.")
    return ExtractedFields.model_validate(extraction.raw_json)


def _allocations(
    session: Session,
    proposal: MatchProposal,
    amount_sen: int,
    edits: dict,
) -> list[Allocation]:
    """Where the money goes: the approver's edit if present, else the proposal's own plan."""
    raw = edits.get("allocations") or proposal.explanation_json.get("allocations")

    if not raw:
        # Fall back to the top candidate, capped at what it still owes.
        candidates = proposal.top_candidates_json or []
        if not candidates:
            raise HTTPException(
                status_code=400,
                detail="Choose an invoice for this payment before approving.",
            )
        best = candidates[0]
        return [
            Allocation(
                invoice_id=int(best["invoice_id"]),
                invoice_no=best["invoice_no"],
                amount_sen=min(amount_sen, int(best["outstanding_sen"])),
            )
        ]

    allocations: list[Allocation] = []
    for item in raw:
        invoice = session.get(Invoice, int(item["invoice_id"]))
        if invoice is None or invoice.tenant_id != proposal.tenant_id:
            raise HTTPException(status_code=400, detail="Unknown invoice in the allocation.")
        allocations.append(
            Allocation(
                invoice_id=invoice.id,
                invoice_no=invoice.invoice_no,
                amount_sen=int(item["amount_sen"]),
            )
        )
    return allocations


def _remaining_sen(session: Session, allocations: list[Allocation]) -> int:
    """What is still outstanding on the invoices this payment touched."""
    total = 0
    for allocation in allocations:
        invoice = session.get(Invoice, allocation.invoice_id)
        if invoice is not None:
            total += invoice.outstanding_sen
    return total


def classification_is_simple(classification: str) -> bool:
    """Only these two can be a one-tap approval; everything else needs a look."""
    return classification in (EXACT_MATCH, PARTIAL_PAYMENT)
