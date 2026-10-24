"""Ledger, customers, payments, dashboard and settings (docs/SPEC.md section 9).

Every query is scoped to the caller's tenant, and a Sales user only ever sees the
customers assigned to them.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.rbac import MANAGE_SETTINGS, VIEW_OWN_CUSTOMERS, has_perm, require
from app.auth.session import Principal, current_principal
from app.db import get_session
from app.media import load_media
from app.models import (
    INVOICE_OPEN,
    INVOICE_PAID,
    INVOICE_PARTIAL,
    PROPOSAL_PENDING,
    ROLE_FINANCE,
    ROLE_SALES,
    Customer,
    Invoice,
    MatchProposal,
    Payment,
    PaymentAllocation,
    Reminder,
    Tenant,
    User,
    utcnow,
)
from app.money import fmt_sen
from app.services.audit import write_audit
from app.services.crypto import mask_phone, decrypt_phone

router = APIRouter(prefix="/api", tags=["ledger"])

OPEN_STATUSES = (INVOICE_OPEN, INVOICE_PARTIAL)


def _own_customer_ids(session: Session, principal: Principal) -> list[int] | None:
    """The customer ids a Sales user may see. None means no restriction."""
    if principal.role != ROLE_SALES:
        return None
    rows = session.execute(
        select(Customer.id).where(
            Customer.tenant_id == principal.tenant_id,
            Customer.assigned_sales_user_id == principal.user_id,
        )
    ).scalars()
    return list(rows)


@router.get("/customers")
def list_customers(
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Customers with their balance, last payment and reminder count."""
    allowed = _own_customer_ids(session, principal)
    stmt = select(Customer).where(Customer.tenant_id == principal.tenant_id)
    if allowed is not None:
        stmt = stmt.where(Customer.id.in_(allowed or [-1]))

    out = []
    for customer in session.execute(stmt.order_by(Customer.name)).scalars():
        balance = session.execute(
            select(func.coalesce(func.sum(Invoice.outstanding_sen), 0)).where(
                Invoice.customer_id == customer.id, Invoice.status.in_(OPEN_STATUSES)
            )
        ).scalar_one()
        last_payment = session.execute(
            select(Payment).where(Payment.customer_id == customer.id).order_by(Payment.paid_at.desc()).limit(1)
        ).scalar_one_or_none()
        reminders = session.execute(
            select(func.count(Reminder.id))
            .join(Invoice, Invoice.id == Reminder.invoice_id)
            .where(Invoice.customer_id == customer.id)
        ).scalar_one()

        out.append(
            {
                "id": customer.id,
                "name": customer.name,
                "aliases": customer.aliases_json or [],
                "language": customer.language,
                "flags": customer.flags_json or [],
                "phone_masked": mask_phone(decrypt_phone(customer.phone_enc))
                if customer.phone_enc
                else None,
                "balance_sen": int(balance),
                "balance_display": fmt_sen(int(balance)),
                "last_payment": (
                    {
                        "amount_display": fmt_sen(last_payment.amount_sen),
                        "paid_at": last_payment.paid_at.isoformat(),
                    }
                    if last_payment
                    else None
                ),
                "reminders_sent": int(reminders),
            }
        )
    return out


@router.get("/invoices")
def list_invoices(
    status: str | None = None,
    overdue_only: bool = False,
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> list[dict]:
    """The ledger, filterable."""
    allowed = _own_customer_ids(session, principal)
    stmt = select(Invoice).where(Invoice.tenant_id == principal.tenant_id)
    if allowed is not None:
        stmt = stmt.where(Invoice.customer_id.in_(allowed or [-1]))
    if status:
        stmt = stmt.where(Invoice.status == status.upper())
    if overdue_only:
        stmt = stmt.where(Invoice.due_date < date.today(), Invoice.status.in_(OPEN_STATUSES))

    invoices = session.execute(stmt.order_by(Invoice.due_date)).scalars()
    return [_invoice_dict(session, invoice) for invoice in invoices]


@router.get("/invoices/{invoice_id}/timeline")
def invoice_timeline(
    invoice_id: int,
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> dict:
    """Everything that ever happened to one invoice, oldest first."""
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="No such invoice.")

    events = [
        {
            "at": invoice.issue_date.isoformat(),
            "kind": "invoice_created",
            "title": f"Invoice {invoice.invoice_no} issued",
            "detail": f"{fmt_sen(invoice.total_sen)}, due {invoice.due_date.isoformat()}",
        }
    ]

    reminders = session.execute(
        select(Reminder).where(Reminder.invoice_id == invoice.id).order_by(Reminder.id)
    ).scalars()
    for reminder in reminders:
        at = reminder.sent_at or reminder.created_at
        events.append(
            {
                "at": at.isoformat(),
                "kind": "reminder",
                "title": f"Reminder ({reminder.status.lower()})",
                "detail": f"Day {reminder.rung:+d} from due date, template {reminder.template_id}",
            }
        )

    allocations = session.execute(
        select(PaymentAllocation, Payment)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.invoice_id == invoice.id)
        .order_by(Payment.paid_at)
    ).all()
    for allocation, payment in allocations:
        user = session.get(User, payment.recorded_by)
        events.append(
            {
                "at": payment.paid_at.isoformat(),
                "kind": "payment",
                "title": f"{fmt_sen(allocation.amount_sen)} received",
                "detail": f"Approved by {user.name if user else 'unknown'}"
                + (f", ref {payment.reference}" if payment.reference else ""),
            }
        )

    events.sort(key=lambda event: event["at"])
    return {"invoice": _invoice_dict(session, invoice), "events": events}


@router.get("/payments")
def list_payments(
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> list[dict]:
    allowed = _own_customer_ids(session, principal)
    stmt = select(Payment).where(Payment.tenant_id == principal.tenant_id)
    if allowed is not None:
        stmt = stmt.where(Payment.customer_id.in_(allowed or [-1]))

    out = []
    for payment in session.execute(stmt.order_by(Payment.paid_at.desc())).scalars():
        customer = session.get(Customer, payment.customer_id)
        user = session.get(User, payment.recorded_by)
        invoice_nos = session.execute(
            select(Invoice.invoice_no)
            .join(PaymentAllocation, PaymentAllocation.invoice_id == Invoice.id)
            .where(PaymentAllocation.payment_id == payment.id)
        ).scalars()
        out.append(
            {
                "id": payment.id,
                "customer_name": customer.name if customer else None,
                "amount_sen": payment.amount_sen,
                "amount_display": fmt_sen(payment.amount_sen),
                "paid_at": payment.paid_at.isoformat(),
                "channel": payment.channel,
                "reference": payment.reference,
                "invoices": list(invoice_nos),
                "recorded_by": user.name if user else None,
            }
        )
    return out


@router.get("/dashboard/summary")
def dashboard_summary(
    principal: Principal = Depends(require(VIEW_OWN_CUSTOMERS)),
    session: Session = Depends(get_session),
) -> dict:
    """The three Today cards plus the KPI strip (docs/SPEC.md sections 9.1 and 9)."""
    tenant_id = principal.tenant_id
    today = date.today()

    pending = session.execute(
        select(func.count(MatchProposal.id)).where(
            MatchProposal.tenant_id == tenant_id, MatchProposal.status == PROPOSAL_PENDING
        )
    ).scalar_one()

    overdue_sen = session.execute(
        select(func.coalesce(func.sum(Invoice.outstanding_sen), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(OPEN_STATUSES),
            Invoice.due_date < today,
        )
    ).scalar_one()

    week_ago = utcnow() - timedelta(days=7)
    received_sen = session.execute(
        select(func.coalesce(func.sum(Payment.amount_sen), 0)).where(
            Payment.tenant_id == tenant_id, Payment.paid_at >= week_ago
        )
    ).scalar_one()

    outstanding_sen = session.execute(
        select(func.coalesce(func.sum(Invoice.outstanding_sen), 0)).where(
            Invoice.tenant_id == tenant_id, Invoice.status.in_(OPEN_STATUSES)
        )
    ).scalar_one()

    decided = session.execute(
        select(MatchProposal).where(
            MatchProposal.tenant_id == tenant_id, MatchProposal.status != PROPOSAL_PENDING
        )
    ).scalars().all()
    total_proposals = session.execute(
        select(func.count(MatchProposal.id)).where(MatchProposal.tenant_id == tenant_id)
    ).scalar_one()
    strong = session.execute(
        select(func.count(MatchProposal.id)).where(
            MatchProposal.tenant_id == tenant_id, MatchProposal.confidence >= 90
        )
    ).scalar_one()
    edited = sum(1 for p in decided if p.decision_note)

    return {
        "cards": {
            "needs_approval": int(pending),
            "overdue_sen": int(overdue_sen),
            "overdue_display": fmt_sen(int(overdue_sen)),
            "received_week_sen": int(received_sen),
            "received_week_display": fmt_sen(int(received_sen)),
        },
        "kpis": {
            "receipts_processed": int(total_proposals),
            "auto_match_rate": round(100 * strong / total_proposals) if total_proposals else 0,
            "human_correction_rate": round(100 * edited / len(decided)) if decided else 0,
            "outstanding_sen": int(outstanding_sen),
            "outstanding_display": fmt_sen(int(outstanding_sen)),
            # Honest framing: the manual baseline is an assumption, not a measurement.
            "seconds_per_receipt_orbit": 20,
            "seconds_per_receipt_manual_assumed": 180,
        },
        "invoice_status": {
            status: int(
                session.execute(
                    select(func.count(Invoice.id)).where(
                        Invoice.tenant_id == tenant_id, Invoice.status == status
                    )
                ).scalar_one()
            )
            for status in (INVOICE_OPEN, INVOICE_PARTIAL, INVOICE_PAID)
        },
    }


@router.get("/settings")
def read_settings(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict:
    tenant = session.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="No such tenant.")
    return {
        "tenant_id": tenant.id,
        "name": tenant.name,
        "whatsapp_number": tenant.whatsapp_number,
        "timezone": tenant.timezone,
        "settings": tenant.settings_json or {},
        # The Settings screen edits this directly, so it has to be readable.
        "finance_approval_limit_sen": _finance_limit_sen(session, tenant.id),
        "editable": has_perm(principal.role, MANAGE_SETTINGS),
    }


def _finance_limit_sen(session: Session, tenant_id: int) -> int:
    """The approval ceiling shared by this tenant's Finance users."""
    limit = session.execute(
        select(func.max(User.approval_limit_sen)).where(
            User.tenant_id == tenant_id, User.role == ROLE_FINANCE
        )
    ).scalar()
    return int(limit or 0)


@router.put("/settings")
def update_settings(
    payload: dict,
    principal: Principal = Depends(require(MANAGE_SETTINGS)),
    session: Session = Depends(get_session),
) -> dict:
    """Owner only. Changing the Finance limit here changes approval routing at once."""
    tenant = session.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="No such tenant.")

    before = dict(tenant.settings_json or {})
    tenant.settings_json = {**before, **(payload.get("settings") or {})}

    limit = payload.get("finance_approval_limit_sen")
    if limit is not None:
        for user in session.execute(
            select(User).where(User.tenant_id == tenant.id, User.role == ROLE_FINANCE)
        ).scalars():
            user.approval_limit_sen = int(limit)

    write_audit(
        session,
        tenant_id=tenant.id,
        actor_type="USER",
        actor_id=principal.user_id,
        action="SETTINGS_UPDATED",
        entity_type="tenant",
        entity_id=tenant.id,
        before=before,
        after=tenant.settings_json,
    )
    session.commit()
    return {
        "settings": tenant.settings_json,
        "finance_approval_limit_sen": _finance_limit_sen(session, tenant.id),
    }


@router.get("/media/{media_ref}")
def read_media(media_ref: str, _: Principal = Depends(current_principal)) -> Response:
    """Serve a stored receipt image to the dashboard."""
    data = load_media(media_ref)
    if data is None:
        raise HTTPException(status_code=404, detail="No such image.")
    return Response(content=data, media_type="image/png")


def _invoice_dict(session: Session, invoice: Invoice) -> dict:
    customer = session.get(Customer, invoice.customer_id)
    days_overdue = (date.today() - invoice.due_date).days
    return {
        "id": invoice.id,
        "invoice_no": invoice.invoice_no,
        "customer_id": invoice.customer_id,
        "customer_name": customer.name if customer else None,
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "total_sen": invoice.total_sen,
        "total_display": fmt_sen(invoice.total_sen),
        "outstanding_sen": invoice.outstanding_sen,
        "outstanding_display": fmt_sen(invoice.outstanding_sen),
        "status": invoice.status,
        "days_overdue": days_overdue if days_overdue > 0 and invoice.status in OPEN_STATUSES else 0,
    }
