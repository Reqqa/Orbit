"""Automated chasing: the overdue ladder and its guards (docs/SPEC.md section 7.4).

All rules, no model. Drafts are created for a human to approve as a batch; nothing
is ever sent without that approval.

There is no background scheduler in the MVP. `build_batch` is driven by the "Run
now" button and would be called by a daily cron in a real deployment, which keeps
the demo deterministic and the dependency list short (decision log 13).
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ACTOR_SYSTEM,
    ACTOR_USER,
    INVOICE_OPEN,
    INVOICE_PARTIAL,
    PROPOSAL_PENDING,
    REMINDER_APPROVED,
    REMINDER_DRAFT,
    REMINDER_SENT,
    Customer,
    Invoice,
    MatchProposal,
    Reminder,
    utcnow,
)
from app.money import fmt_sen
from app.services.audit import write_audit
from app.services.notify import get_sender
from app.templates import messages as templates

log = logging.getLogger("orbit.chasing")

OPEN_STATUSES = (INVOICE_OPEN, INVOICE_PARTIAL)

# Offset in days from the due date -> template. Day +14 has no message on purpose:
# it becomes a "call this customer" task for the owner.
LADDER: list[tuple[int, str | None]] = [
    (-3, templates.REMINDER_HEADS_UP),
    (1, templates.REMINDER_DUE),
    (7, templates.REMINDER_FIRM),
    (14, None),
]

COOLOFF_DAYS = 3
QUIET_START_HOUR = 9
QUIET_END_HOUR = 20


def in_quiet_hours(now: datetime | None = None) -> bool:
    """True outside 9am-8pm, when we must not message anybody."""
    hour = (now or datetime.now()).hour
    return hour < QUIET_START_HOUR or hour >= QUIET_END_HOUR


def build_batch(
    session: Session,
    *,
    tenant_id: int,
    on: date | None = None,
    respect_quiet_hours: bool = False,
) -> dict:
    """Work out who should be chased, and draft the messages. Commits."""
    today = on or date.today()
    drafts: list[Reminder] = []
    skipped: list[dict] = []
    tasks: list[dict] = []

    invoices = session.execute(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id, Invoice.status.in_(OPEN_STATUSES)
        ).order_by(Invoice.due_date)
    ).scalars().all()

    for invoice in invoices:
        offset = (today - invoice.due_date).days
        rung = _rung_for(offset)
        if rung is None:
            continue

        customer = session.get(Customer, invoice.customer_id)
        if customer is None:
            continue

        reason = _skip_reason(session, invoice, customer, today)
        if reason:
            skipped.append(
                {"invoice_no": invoice.invoice_no, "customer": customer.name, "reason": reason}
            )
            continue

        template_id = dict(LADDER)[rung]
        if template_id is None:
            tasks.append(
                {
                    "invoice_no": invoice.invoice_no,
                    "customer": customer.name,
                    "outstanding_display": fmt_sen(invoice.outstanding_sen),
                    "task": "Call this customer personally. No automatic message is sent at day 14.",
                }
            )
            continue

        body = templates.render(
            template_id,
            customer.language,
            customer_name=customer.name,
            invoice_no=invoice.invoice_no,
            amount=fmt_sen(invoice.outstanding_sen),
            due_date=invoice.due_date.isoformat(),
            days_overdue=abs(offset),
        )
        reminder = Reminder(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            rung=rung,
            template_id=template_id,
            body=body,
            status=REMINDER_DRAFT,
        )
        session.add(reminder)
        drafts.append(reminder)

    session.flush()
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_type=ACTOR_SYSTEM,
        action="CHASE_BATCH_DRAFTED",
        entity_type="reminder_batch",
        entity_id=today.isoformat(),
        after={"drafted": len(drafts), "skipped": len(skipped), "tasks": len(tasks)},
    )
    session.commit()

    held = respect_quiet_hours and in_quiet_hours()
    return {
        "date": today.isoformat(),
        "drafts": [_draft_dict(session, r) for r in drafts],
        "skipped": skipped,
        "owner_tasks": tasks,
        "quiet_hours_now": in_quiet_hours(),
        "held_for_quiet_hours": held,
        "note": (
            "Nothing has been sent. Approve the batch to send, and every message uses "
            "a pre-approved template."
        ),
    }


def pending_batch(session: Session, *, tenant_id: int) -> dict:
    """Drafts that are already waiting, without drafting any more."""
    drafts = session.execute(
        select(Reminder).where(
            Reminder.tenant_id == tenant_id, Reminder.status == REMINDER_DRAFT
        ).order_by(Reminder.id)
    ).scalars().all()
    return {
        "date": date.today().isoformat(),
        "drafts": [_draft_dict(session, r) for r in drafts],
        "skipped": [],
        "owner_tasks": [],
        "quiet_hours_now": in_quiet_hours(),
        "held_for_quiet_hours": False,
        "note": "Existing drafts. Press Run now to recalculate today's batch.",
    }


def approve_batch(
    session: Session,
    *,
    tenant_id: int,
    approver_id: int,
    reminder_ids: list[int],
    skip_ids: list[int] | None = None,
) -> dict:
    """Send the approved drafts through the sender. Commits."""
    skip = set(skip_ids or [])
    sender = get_sender(session)
    sent, skipped = 0, 0

    for reminder_id in reminder_ids:
        reminder = session.get(Reminder, reminder_id)
        if reminder is None or reminder.tenant_id != tenant_id:
            continue
        if reminder.status != REMINDER_DRAFT:
            continue
        if reminder_id in skip:
            skipped += 1
            continue

        invoice = session.get(Invoice, reminder.invoice_id)
        customer = session.get(Customer, invoice.customer_id) if invoice else None
        if customer is None:
            continue

        from app.services.crypto import decrypt_phone

        sender.send(
            tenant_id=tenant_id,
            to_phone=decrypt_phone(customer.phone_enc),
            body=reminder.body or "",
        )
        reminder.status = REMINDER_SENT
        reminder.approved_by = approver_id
        reminder.sent_at = utcnow()
        sent += 1

        write_audit(
            session,
            tenant_id=tenant_id,
            actor_type=ACTOR_USER,
            actor_id=approver_id,
            action="REMINDER_SENT",
            entity_type="reminder",
            entity_id=reminder.id,
            after={
                "invoice_id": reminder.invoice_id,
                "rung": reminder.rung,
                "template_id": reminder.template_id,
                "status": REMINDER_SENT,
            },
        )

    write_audit(
        session,
        tenant_id=tenant_id,
        actor_type=ACTOR_USER,
        actor_id=approver_id,
        action="CHASE_BATCH_APPROVED",
        entity_type="reminder_batch",
        entity_id=date.today().isoformat(),
        after={"sent": sent, "skipped": skipped, "status": REMINDER_APPROVED},
    )
    session.commit()
    return {"sent": sent, "skipped": skipped, "simulated": True}


def _rung_for(offset_days: int) -> int | None:
    """Map days-from-due to a ladder rung, exactly."""
    for rung, _template in LADDER:
        if offset_days == rung:
            return rung
    # Day 14 onwards stays an owner task rather than silently stopping.
    if offset_days > 14:
        return None
    return None


def _skip_reason(session: Session, invoice: Invoice, customer: Customer, today: date) -> str | None:
    """The guards from docs/SPEC.md section 7.4."""
    if "disputed" in (customer.flags_json or []):
        return "Customer is flagged as disputed"

    pending = session.execute(
        select(MatchProposal.id).where(
            MatchProposal.tenant_id == invoice.tenant_id,
            MatchProposal.customer_id == customer.id,
            MatchProposal.status == PROPOSAL_PENDING,
        )
    ).scalar()
    if pending:
        return "A payment from this customer is waiting for approval"

    recent = session.execute(
        select(Reminder.id)
        .join(Invoice, Invoice.id == Reminder.invoice_id)
        .where(
            Invoice.customer_id == customer.id,
            Reminder.status == REMINDER_SENT,
            Reminder.sent_at >= utcnow() - timedelta(days=COOLOFF_DAYS),
        )
    ).scalar()
    if recent:
        return f"Already reminded in the last {COOLOFF_DAYS} days"

    already = session.execute(
        select(Reminder.id).where(
            Reminder.invoice_id == invoice.id, Reminder.status == REMINDER_DRAFT
        )
    ).scalar()
    if already:
        return "A draft reminder for this invoice is already waiting"

    return None


def _draft_dict(session: Session, reminder: Reminder) -> dict:
    invoice = session.get(Invoice, reminder.invoice_id)
    customer = session.get(Customer, invoice.customer_id) if invoice else None
    return {
        "id": reminder.id,
        "invoice_no": invoice.invoice_no if invoice else None,
        "customer_name": customer.name if customer else None,
        "language": customer.language if customer else "EN",
        "outstanding_display": fmt_sen(invoice.outstanding_sen) if invoice else None,
        "due_date": invoice.due_date.isoformat() if invoice else None,
        "rung": reminder.rung,
        "tone": _tone(reminder.rung),
        "template_id": reminder.template_id,
        "body": reminder.body,
        "status": reminder.status,
    }


def _tone(rung: int) -> str:
    return {-3: "Friendly heads-up", 1: "Polite reminder", 7: "Firmer reminder"}.get(
        rung, "Owner task"
    )
