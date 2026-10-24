"""The Orbyte hub seam, made visible (docs/SPEC.md section 13).

Orbit consumes company, user, customer and invoice data from the hub, and writes
payment records and activity events back. All of it goes through
`OrbyteConnector`, so this endpoint shows exactly what Orbit reads and writes
across that boundary, and which implementation is answering.

The MVP ships `MockOrbyteConnector`, because live Orbyte access was not available.
The endpoints below are our own documented assumption, not a published API.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.rbac import VIEW_ALL, require
from app.auth.session import Principal
from app.connectors.orbyte import get_connector
from app.db import get_session
from app.models import Tenant
from app.money import fmt_sen

router = APIRouter(prefix="/api/orbyte", tags=["orbyte"])

# The interface we assume of the hub. We define it ourselves, as the brief allows.
ASSUMED_ENDPOINTS = [
    {"method": "GET", "path": "/orbyte/v1/tenants/{id}", "used_for": "company profile, timezone", "direction": "read"},
    {"method": "GET", "path": "/orbyte/v1/users?tenant={id}", "used_for": "users and roles, the RBAC source of truth", "direction": "read"},
    {"method": "GET", "path": "/orbyte/v1/customers?tenant={id}", "used_for": "customer master data and aliases", "direction": "read"},
    {"method": "GET", "path": "/orbyte/v1/invoices?status=open", "used_for": "the invoices every receipt is scored against", "direction": "read"},
    {"method": "POST", "path": "/orbyte/v1/payments", "used_for": "recording an approved payment, with an idempotency key", "direction": "write"},
    {"method": "POST", "path": "/orbyte/v1/activity-log", "used_for": "pushing Orbit's audit events into the hub's shared log", "direction": "write"},
    {"method": "POST", "path": "/orbyte/v1/notifications", "used_for": "optional in-hub alerts", "direction": "write"},
]


@router.get("/status")
def status(
    principal: Principal = Depends(require(VIEW_ALL)),
    session: Session = Depends(get_session),
) -> dict:
    """Which connector is live, what it can see, and what Orbit assumes of the hub."""
    connector = get_connector(session)
    tenant_id = principal.tenant_id

    tenant = connector.get_tenant(tenant_id)
    users = connector.list_users(tenant_id)
    customers = connector.list_customers(tenant_id)
    invoices = connector.list_open_invoices(tenant_id)
    outstanding = sum(int(i["outstanding_sen"]) for i in invoices)

    tenant_count = session.execute(select(func.count(Tenant.id))).scalar_one()

    return {
        "connector": type(connector).__name__,
        "simulated": True,
        "why_simulated": (
            "Live Orbyte access was not available, so the hub interface below is our "
            "own documented assumption and this connector reads the synthetic demo "
            "data. A real connector implements the same interface and nothing else "
            "in Orbit changes."
        ),
        "reads_now": {
            "tenant": tenant.get("name"),
            "users": len(users),
            "customers": len(customers),
            "open_invoices": len(invoices),
            "outstanding_display": fmt_sen(outstanding),
        },
        "writes_back": [
            "a payment record on every approval, keyed by proposal so a retry cannot double-record",
            "an activity event for the hub's shared log",
        ],
        "assumed_interface": ASSUMED_ENDPOINTS,
        "reuse": {
            "tenants_in_this_database": tenant_count,
            "note": (
                "The same module serves any Orbyte SME that invoices on credit through "
                "tenant configuration alone. Switch tenant with the role switcher to see "
                "the same code running a hardware trader, a bakery supplier and a tuition "
                "centre."
            ),
        },
        "what_stays_in_orbit": [
            "the keyed phone HMAC used to recognise a sender, which never leaves this system",
            "receipt images, extractions, match proposals and the hash-chained audit log",
        ],
    }


@router.get("/preview")
def preview(
    principal: Principal = Depends(require(VIEW_ALL)),
    session: Session = Depends(get_session),
) -> dict:
    """A sample of the raw records the connector hands Orbit, labels and all."""
    connector = get_connector(session)
    tenant_id = principal.tenant_id
    return {
        "simulated": True,
        "tenant": connector.get_tenant(tenant_id),
        "users": connector.list_users(tenant_id)[:3],
        "customers": connector.list_customers(tenant_id)[:3],
        "open_invoices": connector.list_open_invoices(tenant_id)[:3],
    }
