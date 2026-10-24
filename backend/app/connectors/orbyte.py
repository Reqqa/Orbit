"""The Orbyte hub adapter (docs/SPEC.md section 13, principle 4 in section 6.3).

Orbit is positioned as an Orbyte app module: the company profile, users and roles,
customer master data and invoices all belong to the Orbyte hub, and Orbit only adds
the receivables workflow on top.

On the live path today: `list_open_invoices` and `list_customers` feed every match
decision, and `record_payment` and `push_activity` run on every approval. The other
three methods - `get_tenant`, `list_users` and `send_notification` - are implemented
and exercised by `/api/orbyte/status` and `/preview`, but Orbit still reads tenant
and user rows directly for the simulated login, because those are the platform
foundations the brief says may be simulated.

**The endpoints below are our own documented assumption, not a published contract.**
Live Orbyte access was not available while building this MVP, and the brief allows us
to define the interface ourselves. The method names map one to one onto the endpoints
written down in SPEC section 13:

    get_tenant          -> GET  /orbyte/v1/tenants/{id}
    list_users          -> GET  /orbyte/v1/users?tenant={id}
    list_customers      -> GET  /orbyte/v1/customers?tenant={id}
    list_open_invoices  -> GET  /orbyte/v1/invoices?status=open
    record_payment      -> POST /orbyte/v1/payments          (idempotency key)
    push_activity       -> POST /orbyte/v1/activity-log
    send_notification   -> POST /orbyte/v1/notifications

Because the interface is a seam rather than a guess baked into call sites, swapping
`MockOrbyteConnector` for a real HTTP connector is a one-file change: the same module
serves any Orbyte SME with a config change, and no caller has to be rewritten.

Two rules hold for everything returned from here:
  - money is integer sen, same as the database columns
  - every dict carries `"simulated": True`, so nothing in the demo can be mistaken
    for a real hub read or a real hub write (CLAUDE.md: label simulated things)
"""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Invoice, Tenant, User

# Statuses that count as "open" for the assumed GET /invoices?status=open.
_OPEN_STATUSES = ("OPEN", "PARTIAL")


class OrbyteConnector(ABC):
    """The hub interface Orbit codes against. One method per assumed endpoint."""

    @abstractmethod
    def get_tenant(self, tenant_id: int) -> dict[str, Any]:
        """Company profile: name, WhatsApp number, timezone, settings."""

    @abstractmethod
    def list_users(self, tenant_id: int) -> list[dict[str, Any]]:
        """Users and their roles. The hub is the RBAC source of truth."""

    @abstractmethod
    def list_customers(self, tenant_id: int) -> list[dict[str, Any]]:
        """Customer master data, so Orbit never re-enters it."""

    @abstractmethod
    def list_open_invoices(
        self, tenant_id: int, customer_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Open and partially paid invoices, optionally for one customer."""

    @abstractmethod
    def record_payment(
        self, tenant_id: int, payment: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        """Record an approved payment against the hub. `amount_sen` is integer sen."""

    @abstractmethod
    def push_activity(self, tenant_id: int, event: dict[str, Any]) -> dict[str, Any]:
        """Push one audit event into the hub's shared activity log."""

    @abstractmethod
    def send_notification(
        self, tenant_id: int, notification: dict[str, Any]
    ) -> dict[str, Any]:
        """Raise an in-hub alert for a user."""


class MockOrbyteConnector(OrbyteConnector):
    """The MVP connector: reads the local SQLite rows that stand in for the hub.

    Reads are real reads of the seeded demo data, scoped by `tenant_id`. Writes are
    deliberately no-ops that echo back what they were given: the real hub write is out
    of scope for this MVP, and Orbit's own tables remain the system of record for the
    demo. Nothing here ever moves money.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_tenant(self, tenant_id: int) -> dict[str, Any]:
        """Company profile for one tenant, or an empty simulated row if unknown."""
        tenant = self._session.get(Tenant, tenant_id)
        if tenant is None:
            return {"id": tenant_id, "found": False, "simulated": True}
        return {
            "id": tenant.id,
            "name": tenant.name,
            "whatsapp_number": tenant.whatsapp_number,
            "timezone": tenant.timezone,
            "settings_json": tenant.settings_json,
            "found": True,
            "simulated": True,
        }

    def list_users(self, tenant_id: int) -> list[dict[str, Any]]:
        """Users and roles for one tenant. Phone columns are not exposed."""
        rows = self._session.scalars(
            select(User).where(User.tenant_id == tenant_id).order_by(User.id)
        ).all()
        return [
            {
                "id": u.id,
                "tenant_id": u.tenant_id,
                "name": u.name,
                "role": u.role,
                "approval_limit_sen": u.approval_limit_sen,
                "simulated": True,
            }
            for u in rows
        ]

    def list_customers(self, tenant_id: int) -> list[dict[str, Any]]:
        """Customer master data for one tenant. Phone columns are not exposed."""
        rows = self._session.scalars(
            select(Customer).where(Customer.tenant_id == tenant_id).order_by(Customer.id)
        ).all()
        return [
            {
                "id": c.id,
                "tenant_id": c.tenant_id,
                "name": c.name,
                "aliases_json": c.aliases_json,
                "language": c.language,
                "assigned_sales_user_id": c.assigned_sales_user_id,
                "flags_json": c.flags_json,
                "simulated": True,
            }
            for c in rows
        ]

    def list_open_invoices(
        self, tenant_id: int, customer_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Open/partial invoices for one tenant, oldest due date first."""
        stmt = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(_OPEN_STATUSES),
        )
        if customer_id is not None:
            stmt = stmt.where(Invoice.customer_id == customer_id)
        rows = self._session.scalars(stmt.order_by(Invoice.due_date, Invoice.id)).all()
        return [
            {
                "id": i.id,
                "tenant_id": i.tenant_id,
                "customer_id": i.customer_id,
                "invoice_no": i.invoice_no,
                "issue_date": i.issue_date.isoformat(),
                "due_date": i.due_date.isoformat(),
                "total_sen": i.total_sen,
                "outstanding_sen": i.outstanding_sen,
                "status": i.status,
                "simulated": True,
            }
            for i in rows
        ]

    def record_payment(
        self, tenant_id: int, payment: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        """No-op echo. The real POST /orbyte/v1/payments is out of scope for the MVP."""
        return {
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
            "payment": payment,
            "simulated": True,
            "accepted": True,
        }

    def push_activity(self, tenant_id: int, event: dict[str, Any]) -> dict[str, Any]:
        """No-op echo. The hub activity log is written by the real connector, not this one."""
        return {
            "tenant_id": tenant_id,
            "event": event,
            "simulated": True,
            "accepted": True,
        }

    def send_notification(
        self, tenant_id: int, notification: dict[str, Any]
    ) -> dict[str, Any]:
        """No-op echo. In-hub alerts are out of scope for the MVP."""
        return {
            "tenant_id": tenant_id,
            "notification": notification,
            "simulated": True,
            "accepted": True,
        }


def get_connector(session: Session) -> OrbyteConnector:
    """Return the connector Orbit should use. The single seam for a real hub client."""
    return MockOrbyteConnector(session)
