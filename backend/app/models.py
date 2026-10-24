"""Database tables (docs/SPEC.md section 8).

Rules that hold for every table here:
  - all money columns are integer sen and end in `_sen`
  - every business table carries `tenant_id` and every query must scope by it
  - phone numbers are stored twice: `*_hmac` for lookup, `*_enc` for sending replies
  - `audit_log` is append-only and hash-chained; nothing updates or deletes it
"""

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# --- Roles (docs/SPEC.md section 4) ---
ROLE_OWNER = "OWNER"
ROLE_FINANCE = "FINANCE"
ROLE_SALES = "SALES"
ROLES = (ROLE_OWNER, ROLE_FINANCE, ROLE_SALES)

# --- Invoice status ---
INVOICE_OPEN = "OPEN"
INVOICE_PARTIAL = "PARTIAL"
INVOICE_PAID = "PAID"
INVOICE_VOID = "VOID"

# --- Proposal status ---
PROPOSAL_PENDING = "PENDING"
PROPOSAL_APPROVED = "APPROVED"
PROPOSAL_REJECTED = "REJECTED"
PROPOSAL_EXPIRED = "EXPIRED"

# --- Reminder status ---
REMINDER_DRAFT = "DRAFT"
REMINDER_APPROVED = "APPROVED"
REMINDER_SENT = "SENT"
REMINDER_FAILED = "FAILED"

# --- Audit actor types ---
ACTOR_USER = "USER"
ACTOR_SYSTEM = "SYSTEM"
ACTOR_AI = "AI"
ACTOR_CUSTOMER = "CUSTOMER"


def utcnow() -> datetime:
    """Naive UTC timestamp.

    Naive on purpose: SQLite strips tzinfo on read, and the audit hash chain
    re-hashes stored values, so what goes in must come back out identical.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    whatsapp_number: Mapped[str] = mapped_column(String(32), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kuala_Lumpur")
    # Per-tenant configuration: match weights, thresholds, chase ladder, quiet hours.
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))
    phone_hmac: Mapped[str | None] = mapped_column(String(64), index=True)
    phone_enc: Mapped[str | None] = mapped_column(Text)
    approval_limit_sen: Mapped[int] = mapped_column(Integer, default=0)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    aliases_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    phone_hmac: Mapped[str] = mapped_column(String(64), index=True)
    phone_enc: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(4), default="EN")  # EN | BM | ZH
    assigned_sales_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)  # e.g. ["disputed"]


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_no", name="uq_invoice_no_per_tenant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    invoice_no: Mapped[str] = mapped_column(String(32))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    total_sen: Mapped[int] = mapped_column(Integer)
    outstanding_sen: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default=INVOICE_OPEN)

    customer: Mapped[Customer] = relationship(lazy="joined")


class WhatsappMessage(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    # Meta retries deliveries, so this is the idempotency key.
    wa_message_id: Mapped[str] = mapped_column(String(128), unique=True)
    direction: Mapped[str] = mapped_column(String(4), default="IN")  # IN | OUT
    from_hmac: Mapped[str | None] = mapped_column(String(64), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    type: Mapped[str] = mapped_column(String(16))  # image | text
    media_ref: Mapped[str | None] = mapped_column(String(255))  # reference only, never bytes
    text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="RECEIVED")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_messages.id"), index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_name: Mapped[str] = mapped_column(String(64))
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MatchProposal(Base):
    __tablename__ = "match_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_messages.id"))
    extraction_id: Mapped[int | None] = mapped_column(ForeignKey("extractions.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    classification: Mapped[str] = mapped_column(String(24))
    top_candidates_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=PROPOSAL_PENDING)
    requested_approver_role: Mapped[str] = mapped_column(String(16), default=ROLE_OWNER)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    amount_sen: Mapped[int] = mapped_column(Integer)
    paid_at: Mapped[datetime] = mapped_column(DateTime)
    channel: Mapped[str | None] = mapped_column(String(64))
    reference: Mapped[str | None] = mapped_column(String(128))
    transaction_id: Mapped[str | None] = mapped_column(String(128), index=True)
    # One payment per approved proposal: the idempotency guard on recording.
    proposal_id: Mapped[int] = mapped_column(ForeignKey("match_proposals.id"), unique=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_sen: Mapped[int] = mapped_column(Integer)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    rung: Mapped[int] = mapped_column(Integer)  # offset in days from due date: -3, 1, 7, 14
    template_id: Mapped[str] = mapped_column(String(32))
    body: Mapped[str | None] = mapped_column(Text)  # rendered preview, for the batch screen
    status: Mapped[str] = mapped_column(String(10), default=REMINDER_DRAFT)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    """Append-only, hash-chained. One chain per tenant, ordered by id.

    `before_json` and `after_json` are canonical JSON *text*, not JSON columns,
    so the hash can be recomputed byte for byte during verification.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(10))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(48))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    hash_prev: Mapped[str] = mapped_column(String(64))
    hash_self: Mapped[str] = mapped_column(String(64), unique=True)
