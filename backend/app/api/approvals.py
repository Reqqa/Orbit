"""The approval inbox and the decision endpoint (docs/SPEC.md section 9.2)."""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.rbac import VIEW_OWN_CUSTOMERS, require
from app.auth.session import Principal, current_principal
from app.db import get_session
from app.models import (
    PROPOSAL_PENDING,
    ROLE_SALES,
    Customer,
    Extraction,
    MatchProposal,
    WhatsappMessage,
)
from app.money import fmt_sen
from app.services.approval import decide_proposal
from app.services.proposals import visible_proposals

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    status: str | None = PROPOSAL_PENDING,
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Everything waiting for a decision, with all of its evidence attached.

    Sales can read this, restricted to their own customers (docs/SPEC.md section 9.9).
    They are refused at the decision endpoint, not here, so the refusal is something a
    person actually sees rather than an empty screen.
    """
    proposals = visible_proposals(session, tenant_id=principal.tenant_id, status=status)
    allowed = _own_customer_ids(session, principal)
    if allowed is not None:
        proposals = [p for p in proposals if p.customer_id in allowed]
    return [_serialise(session, proposal) for proposal in proposals]


def _own_customer_ids(session: Session, principal: Principal) -> set[int] | None:
    """Customer ids a Sales user may see. None means no restriction."""
    if principal.role != ROLE_SALES:
        return None
    rows = session.execute(
        select(Customer.id).where(
            Customer.tenant_id == principal.tenant_id,
            Customer.assigned_sales_user_id == principal.user_id,
        )
    ).scalars()
    return set(rows)


@router.get("/{proposal_id}")
def read_approval(
    proposal_id: int,
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> dict:
    proposal = session.get(MatchProposal, proposal_id)
    if proposal is None or proposal.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="That approval item does not exist.")
    allowed = _own_customer_ids(session, principal)
    if allowed is not None and proposal.customer_id not in allowed:
        raise HTTPException(status_code=404, detail="That approval item does not exist.")
    return _serialise(session, proposal)


@router.post("/{proposal_id}/decision")
def decide(
    proposal_id: int,
    payload: dict = Body(...),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict:
    """Approve or reject. Role and amount limit are enforced here, server-side."""
    return decide_proposal(
        session,
        principal,
        proposal_id=proposal_id,
        decision=str(payload.get("decision", "")).lower(),
        note=payload.get("note"),
        edits=payload.get("edits"),
    )


def _serialise(session: Session, proposal: MatchProposal) -> dict:
    extraction = (
        session.get(Extraction, proposal.extraction_id) if proposal.extraction_id else None
    )
    message = session.get(WhatsappMessage, proposal.message_id)
    customer = session.get(Customer, proposal.customer_id) if proposal.customer_id else None
    fields = extraction.raw_json if extraction else {}
    amount_sen = fields.get("amount_sen")

    return {
        "id": proposal.id,
        "classification": proposal.classification,
        "confidence": proposal.confidence,
        "status": proposal.status,
        "requested_approver_role": proposal.requested_approver_role,
        "created_at": proposal.created_at.isoformat(),
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
        "decision_note": proposal.decision_note,
        "customer": (
            {"id": customer.id, "name": customer.name, "language": customer.language}
            if customer
            else None
        ),
        "amount_sen": amount_sen,
        "amount_display": fmt_sen(amount_sen) if amount_sen else None,
        "extracted": fields,
        "model_name": extraction.model_name if extraction else None,
        "candidates": proposal.top_candidates_json or [],
        "explanation": proposal.explanation_json or {},
        "media_url": (
            f"/api/media/{message.media_ref}" if message and message.media_ref else None
        ),
        "simulated_channel": bool(message.simulated) if message else True,
    }
