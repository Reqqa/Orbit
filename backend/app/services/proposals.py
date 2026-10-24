"""The pipeline from an inbound message to a proposal waiting for a human.

  extract (AI)  ->  score (rules)  ->  classify (rules)  ->  proposal  ->  inbox

Only the first step uses a model. Everything after it is deterministic, which is
why the explanation shown to the owner can be trusted (docs/SPEC.md section 6.3).
"""

import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.orbyte import OrbyteConnector, get_connector
from app.models import (
    ACTOR_AI,
    ACTOR_SYSTEM,
    INVOICE_OPEN,
    INVOICE_PARTIAL,
    PROPOSAL_APPROVED,
    PROPOSAL_PENDING,
    PROPOSAL_REJECTED,
    ROLE_FINANCE,
    ROLE_OWNER,
    Customer,
    Extraction,
    Invoice,
    MatchProposal,
    Payment,
    Tenant,
    User,
    WhatsappMessage,
)
from app.schemas import (
    NOT_A_RECEIPT,
    THRESHOLD_STRONG,
    Candidate,
    CustomerView,
    Decision,
    ExtractedFields,
    InvoiceView,
)
from app.services import classify as classify_service
from app.services import matching
from app.services.audit import write_audit
from app.services.extraction import extract_for_message
from app.services.notify import notify_customer
from app.templates import messages as templates

log = logging.getLogger("orbit.proposals")

OPEN_STATUSES = (INVOICE_OPEN, INVOICE_PARTIAL)


def process_message(
    session: Session,
    *,
    message_id: int,
    image_bytes: bytes | None = None,
) -> MatchProposal | None:
    """Run one inbound message all the way to a pending proposal. Commits once."""
    message = session.get(WhatsappMessage, message_id)
    if message is None:
        raise ValueError(f"message {message_id} not found")

    if image_bytes is None:
        # A text-only message is logged and left for a human; there is nothing to read.
        write_audit(
            session,
            tenant_id=message.tenant_id,
            actor_type=ACTOR_SYSTEM,
            action="MESSAGE_IGNORED",
            entity_type="whatsapp_message",
            entity_id=message.id,
            after={"reason": "no image attached"},
        )
        session.commit()
        return None

    extraction, fields = extract_for_message(
        session, message_id=message.id, image_bytes=image_bytes
    )
    write_audit(
        session,
        tenant_id=message.tenant_id,
        actor_type=ACTOR_AI,
        actor_id=extraction.model_name,
        action="RECEIPT_READ",
        entity_type="extraction",
        entity_id=extraction.id,
        after={
            "is_payment_receipt": fields.is_payment_receipt,
            "amount_sen": fields.amount_sen,
            "reference_text": fields.reference_text,
            "lowest_key_confidence": fields.lowest_key_confidence,
        },
    )

    customer = session.get(Customer, message.customer_id) if message.customer_id else None
    decision = decide(session, tenant_id=message.tenant_id, customer=customer, fields=fields)

    proposal = MatchProposal(
        tenant_id=message.tenant_id,
        message_id=message.id,
        extraction_id=extraction.id,
        customer_id=customer.id if customer else None,
        classification=decision.classification,
        top_candidates_json=[c.model_dump() for c in decision.candidates[:5]],
        confidence=decision.confidence,
        # The allocation plan rides along with the explanation so the approval
        # endpoint can apply exactly what the approver was shown.
        explanation_json={
            **decision.explanation,
            "allocations": [a.model_dump() for a in decision.allocations],
        },
        status=PROPOSAL_PENDING,
        requested_approver_role=required_role(
            session,
            tenant_id=message.tenant_id,
            amount_sen=fields.amount_sen or 0,
            confidence=decision.confidence,
            is_exception=decision.is_exception,
        ),
    )
    session.add(proposal)
    session.flush()

    write_audit(
        session,
        tenant_id=message.tenant_id,
        actor_type=ACTOR_SYSTEM,
        action="PROPOSAL_CREATED",
        entity_type="match_proposal",
        entity_id=proposal.id,
        after={
            "classification": decision.classification,
            "confidence": decision.confidence,
            "requested_approver_role": proposal.requested_approver_role,
            "allocations": [a.model_dump() for a in decision.allocations],
        },
    )

    # Not a receipt: reply politely and record nothing (docs/SPEC.md section 7.3).
    if decision.classification == NOT_A_RECEIPT:
        proposal.status = PROPOSAL_REJECTED
        proposal.decision_note = "Not a payment receipt. Replied automatically, nothing recorded."
        if customer is not None:
            notify_customer(
                session,
                tenant_id=message.tenant_id,
                customer=customer,
                template_id=templates.NOT_A_RECEIPT,
                customer_name=customer.name,
            )

    session.commit()
    log.info("proposal %s is %s", proposal.id, proposal.classification)
    return proposal


def decide(
    session: Session,
    *,
    tenant_id: int,
    customer: Customer | None,
    fields: ExtractedFields,
) -> Decision:
    """Score and classify one extraction. The only database-aware part of the decision."""
    if not fields.usable_for_matching:
        # Nothing to score against; classify() routes this to a human.
        return classify_service.classify(fields, [])

    # Hub data comes through the connector, never from a direct query
    # (docs/SPEC.md section 6.3 principle 4). Swapping in a real Orbyte client
    # changes this one line and nothing else in the decision path.
    connector = get_connector(session)
    views = [
        invoice_view_from_hub(row)
        for row in connector.list_open_invoices(tenant_id, customer.id if customer else None)
    ]
    customer_view = customer_view_from_hub(connector, tenant_id, customer) if customer else None

    candidates: list[Candidate] = matching.score_candidates(
        fields,
        views,
        customer_view,
        weights=match_weights(session, tenant_id),
        sender_phone_hmac=customer.phone_hmac if customer else None,
    )

    multi = matching.find_multi_invoice_combination(fields, views)
    duplicate_id, duplicate_kind = find_duplicate(
        session, tenant_id=tenant_id, fields=fields, customer=customer
    )

    decision = classify_service.classify(
        fields,
        candidates,
        duplicate_payment_id=duplicate_id,
        multi_allocations=multi,
    )

    if duplicate_kind == "proposal":
        # The earlier copy has not been approved, so nothing is recorded yet. Say so
        # rather than letting the explanation imply a payment already exists.
        decision.explanation = {
            **decision.explanation,
            "next_step": (
                f"The same transaction already arrived and is waiting for a decision "
                f"(item {duplicate_id}). Handle that one and reject this copy."
            ),
        }

    return decision


def open_invoices(
    session: Session, *, tenant_id: int, customer_id: int | None = None
) -> list[Invoice]:
    """Open and partly paid invoices, for one customer or the whole tenant."""
    stmt = select(Invoice).where(
        Invoice.tenant_id == tenant_id, Invoice.status.in_(OPEN_STATUSES)
    )
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    return list(session.execute(stmt.order_by(Invoice.due_date, Invoice.invoice_no)).scalars())


def invoice_view_from_hub(row: dict) -> InvoiceView:
    """Turn one hub invoice record into the shape the scorer takes."""
    return InvoiceView(
        id=int(row["id"]),
        invoice_no=row["invoice_no"],
        issue_date=date.fromisoformat(row["issue_date"]),
        due_date=date.fromisoformat(row["due_date"]),
        total_sen=int(row["total_sen"]),
        outstanding_sen=int(row["outstanding_sen"]),
    )


def customer_view_from_hub(
    connector: OrbyteConnector, tenant_id: int, customer: Customer
) -> CustomerView:
    """Customer master data from the hub, with Orbit's own sender index attached.

    The hub holds the name, aliases and language. It does not hold `phone_hmac`:
    that is Orbit's own keyed index for working out who a WhatsApp message came
    from, and it deliberately never leaves this system (docs/SPEC.md section 10).
    """
    row = next((c for c in connector.list_customers(tenant_id) if c["id"] == customer.id), None)
    if row is None:
        return to_customer_view(customer)
    return CustomerView(
        id=int(row["id"]),
        name=row["name"],
        aliases=list(row.get("aliases_json") or []),
        phone_hmac=customer.phone_hmac,
        language=row.get("language") or "EN",
    )


def to_invoice_view(invoice: Invoice) -> InvoiceView:
    return InvoiceView(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        total_sen=invoice.total_sen,
        outstanding_sen=invoice.outstanding_sen,
    )


def to_customer_view(customer: Customer) -> CustomerView:
    return CustomerView(
        id=customer.id,
        name=customer.name,
        aliases=list(customer.aliases_json or []),
        phone_hmac=customer.phone_hmac,
        language=customer.language,
    )


def match_weights(session: Session, tenant_id: int) -> dict[str, int] | None:
    """Per-tenant scorecard weights, if the tenant has configured any."""
    tenant = session.get(Tenant, tenant_id)
    settings = (tenant.settings_json or {}) if tenant else {}
    weights = settings.get("match_weights")
    return weights if isinstance(weights, dict) and weights else None


def find_duplicate(
    session: Session,
    *,
    tenant_id: int,
    fields: ExtractedFields,
    customer: Customer | None,
) -> tuple[int | None, str | None]:
    """Has this payment already arrived? Returns (id, "payment" | "proposal").

    Two ways to be a duplicate (docs/SPEC.md section 7.3):
      * a payment with the same transaction id, or the same amount from the same
        customer within 24 hours, is already recorded
      * the very same receipt arrived earlier and is still waiting for a decision,
        so nothing is recorded yet but it must not be recorded twice
    """
    if fields.transaction_id:
        recorded = session.execute(
            select(Payment.id).where(
                Payment.tenant_id == tenant_id,
                Payment.transaction_id == fields.transaction_id,
            )
        ).scalar()
        if recorded:
            return int(recorded), "payment"

        seen = session.execute(
            select(MatchProposal.id)
            .join(Extraction, Extraction.id == MatchProposal.extraction_id)
            .where(
                MatchProposal.tenant_id == tenant_id,
                MatchProposal.status.in_((PROPOSAL_PENDING, PROPOSAL_APPROVED)),
                Extraction.raw_json["transaction_id"].as_string() == fields.transaction_id,
            )
            .order_by(MatchProposal.id)
            .limit(1)
        ).scalar()
        if seen:
            return int(seen), "proposal"

    if customer is None or not fields.amount_sen or fields.transaction_datetime is None:
        return None, None

    paid_at = fields.transaction_datetime.replace(tzinfo=None)
    window = timedelta(hours=24)
    nearby = session.execute(
        select(Payment.id).where(
            Payment.tenant_id == tenant_id,
            Payment.customer_id == customer.id,
            Payment.amount_sen == fields.amount_sen,
            Payment.paid_at >= paid_at - window,
            Payment.paid_at <= paid_at + window,
        )
    ).scalar()
    return (int(nearby), "payment") if nearby else (None, None)


def required_role(
    session: Session,
    *,
    tenant_id: int,
    amount_sen: int,
    confidence: int,
    is_exception: bool,
) -> str:
    """Finance for small, strong, ordinary matches. Owner for everything else."""
    if is_exception or confidence < THRESHOLD_STRONG:
        return ROLE_OWNER

    limit = session.execute(
        select(func.max(User.approval_limit_sen)).where(
            User.tenant_id == tenant_id, User.role == ROLE_FINANCE
        )
    ).scalar()

    if limit and amount_sen <= int(limit):
        return ROLE_FINANCE
    return ROLE_OWNER


def visible_proposals(session: Session, *, tenant_id: int, status: str | None = PROPOSAL_PENDING):
    """Proposals for one tenant, newest first."""
    stmt = select(MatchProposal).where(MatchProposal.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(MatchProposal.status == status)
    return list(session.execute(stmt.order_by(MatchProposal.id.desc())).scalars())
