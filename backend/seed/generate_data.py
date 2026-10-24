"""Generate the synthetic demo dataset (docs/SPEC.md section 8.1).

    python -m seed.generate_data [--reset]

Everything here is deterministic: one fixed random seed, and due dates anchored to
today with hand-picked offsets, so every demo run shows the judges the same numbers.
No real customers, no real phone numbers, no real banks.
"""

import argparse
import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    ACTOR_SYSTEM,
    INVOICE_OPEN,
    INVOICE_PAID,
    INVOICE_PARTIAL,
    ROLE_FINANCE,
    ROLE_OWNER,
    ROLE_SALES,
    AuditLog,
    Customer,
    Invoice,
    Tenant,
    User,
)
from app.schemas import (
    DEFAULT_WEIGHTS,
    MIN_FIELD_CONFIDENCE,
    THRESHOLD_CANDIDATE,
    THRESHOLD_LIKELY,
    THRESHOLD_STRONG,
)
from app.services.audit import write_audit
from app.services.crypto import encrypt_phone, phone_hmac

SEED = 20260124  # fixed on purpose: identical dataset on every run

# --- Tenant definitions (name, whatsapp number, how many invoices) ---
# Three trades, to prove reusability. Tenant 1 is the one we demo on, so it has most.
TENANTS = [
    ("Sin Heng Hardware Trading", "+60127000001", 40),
    ("Roti Lima Bakery Supplies", "+60127000002", 22),
    ("Cahaya Tuition Centre", "+60127000003", 18),
]

# Per-tenant staff. OWNER limit 0 means unlimited; FINANCE is capped at RM 2,000.
STAFF = [
    [
        ("Lim Wei Keong", ROLE_OWNER, 0),
        ("Nurul Aisyah Binti Rahim", ROLE_FINANCE, 200_000),
        ("Ravi Chandran", ROLE_SALES, 0),
    ],
    [
        ("Siti Zubaidah Binti Hassan", ROLE_OWNER, 0),
        ("Chong Mei Ling", ROLE_FINANCE, 200_000),
        ("Ahmad Firdaus Bin Yusof", ROLE_SALES, 0),
    ],
    [
        ("Goh Chin Hoe", ROLE_OWNER, 0),
        ("Devi Shanmugam", ROLE_FINANCE, 200_000),
        ("Tengku Hafiz Bin Ismail", ROLE_SALES, 0),
    ],
]

# (full name, the short form customers actually write on a transfer slip)
PEOPLE: list[tuple[str, str]] = [
    ("Tan Ah Seng", "Ah Seng"),
    ("Lee Chong Wei", "Chong Wei"),
    ("Wong Ah Fook", "Ah Fook"),
    ("Ng Siew Lan", "Siew Lan"),
    ("Khoo Boon Hwa", "Boon Hwa"),
    ("Chan Ah Kow", "Ah Kow"),
    ("Yap Mei Yee", "Mei Yee"),
    ("Teoh Keng Soon", "Keng Soon"),
    ("Ooi Ah Lek", "Ah Lek"),
    ("Low Kah Hoe", "Kah Hoe"),
    ("Chee Hwa Peng", "Hwa Peng"),
    ("Mohd Razak Bin Omar", "Razak"),
    ("Siti Khadijah", "Khadijah"),
    ("Abdul Halim Bin Salleh", "Halim"),
    ("Zainal Abidin", "Zainal"),
    ("Norliza Binti Ibrahim", "Norliza"),
    ("Hamzah Bin Daud", "Hamzah"),
    ("Faridah Binti Mokhtar", "Faridah"),
    ("Syed Mustafa", "Mustafa"),
    ("Rosnah Binti Kamal", "Rosnah"),
    ("Azman Bin Sulaiman", "Azman"),
    ("Mariam Binti Jusoh", "Mariam"),
    ("Muthu Samy", "Muthu"),
    ("Kumaran Pillai", "Kumaran"),
    ("Vijaya Letchumi", "Vijaya"),
    ("Suresh Nadarajah", "Suresh"),
    ("Anbalagan Raju", "Anba"),
    ("Priya Thevi", "Priya"),
    ("Gurmit Singh", "Gurmit"),
    ("Rajendran Kutty", "Rajen"),
]

SUFFIXES = [
    "Enterprise",
    "Trading",
    "Sdn Bhd",
    "Hardware",
    "Supplies",
    "Bakery",
    "Marketing",
    "Resources",
    "Services",
    "Mini Market",
]

LANGUAGES = ["EN", "EN", "BM", "ZH", "BM", "EN", "ZH"]

# Days past the due date (negative = not due yet). Hand-picked so every bucket the
# dashboard shows is populated, including the 1, 7 and 14+ day cases the spec names.
DUE_OFFSETS = [-12, -5, -2, 1, 2, 4, 7, 9, 11, 14, 21, 35, -8, 1, 7, 14]


def tenant_settings() -> dict:
    """Per-tenant config: match weights (7.2), chase ladder (7.4), quiet hours, thresholds."""
    return {
        "weights": dict(DEFAULT_WEIGHTS),
        "thresholds": {
            "strong": THRESHOLD_STRONG,
            "likely": THRESHOLD_LIKELY,
            "candidate": THRESHOLD_CANDIDATE,
            "min_field_confidence": MIN_FIELD_CONFIDENCE,
        },
        "chase_ladder": [
            {"offset_days": -3, "template_id": "HEADS_UP", "approval": "BATCH"},
            {"offset_days": 1, "template_id": "POLITE", "approval": "BATCH"},
            {"offset_days": 7, "template_id": "FIRM", "approval": "BATCH"},
            {"offset_days": 14, "template_id": "CALL_TASK", "approval": "NONE"},
        ],
        "quiet_hours": {"start_hour": 9, "end_hour": 20},
    }


def _phone(rng: random.Random, used: set[str]) -> str:
    """A fictional Malaysian mobile in the 60 1x xxx xxxx shape, never reused."""
    while True:
        number = f"601{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}"
        if number not in used:
            used.add(number)
            return number


def _amount_sen(rng: random.Random) -> int:
    """RM 80.00 - RM 6,000.00 in integer sen, rounded to the nearest 50 sen."""
    return rng.randrange(160, 12_001) * 50


def seed_all(session: Session) -> None:
    """Insert the whole synthetic dataset plus one SEED_CREATED audit row per tenant."""
    rng = random.Random(SEED)
    today = date.today()
    used_phones: set[str] = set()
    names = rng.sample([f"{person} {suffix}" for person, _ in PEOPLE for suffix in SUFFIXES], 75)
    nickname = dict(PEOPLE)

    for t_index, (tenant_name, wa_number, invoice_count) in enumerate(TENANTS):
        tenant = Tenant(
            name=tenant_name,
            whatsapp_number=wa_number,
            settings_json=tenant_settings(),
        )
        session.add(tenant)
        session.flush()

        sales_user_id = None
        for staff_name, role, limit in STAFF[t_index]:
            number = _phone(rng, used_phones)
            user = User(
                tenant_id=tenant.id,
                name=staff_name,
                role=role,
                phone_hmac=phone_hmac(number),
                phone_enc=encrypt_phone(number),
                approval_limit_sen=limit,
            )
            session.add(user)
            session.flush()
            if role == ROLE_SALES:
                sales_user_id = user.id

        customers: list[Customer] = []
        for c_index in range(25):
            name = names[t_index * 25 + c_index]
            person = name.rsplit(" ", 1)[0]  # strip the business suffix
            nick = nickname.get(person)
            number = _phone(rng, used_phones)
            customer = Customer(
                tenant_id=tenant.id,
                name=name,
                aliases_json=[nick] if nick and c_index % 3 == 0 else [],
                phone_hmac=phone_hmac(number),
                phone_enc=encrypt_phone(number),
                language=LANGUAGES[c_index % len(LANGUAGES)],
                # Roughly half the book is assigned to this tenant's sales rep.
                assigned_sales_user_id=sales_user_id if c_index % 2 == 0 else None,
                flags_json=["disputed"] if c_index in (4, 17) else [],
            )
            session.add(customer)
            customers.append(customer)
        session.flush()

        for i_index in range(invoice_count):
            customer = customers[i_index % 25]
            total_sen = _amount_sen(rng)
            # Cycle OPEN / OPEN / PARTIAL / PAID so every status is well represented.
            slot = i_index % 4
            if slot == 3:
                status, outstanding_sen = INVOICE_PAID, 0
            elif slot == 2:
                status = INVOICE_PARTIAL
                paid_sen = (total_sen * rng.randrange(20, 81)) // 100
                # Strictly between 0 and total_sen, whatever the rounding did.
                outstanding_sen = min(max(total_sen - paid_sen, 1), total_sen - 1)
            else:
                status, outstanding_sen = INVOICE_OPEN, total_sen

            due_date = today - timedelta(days=DUE_OFFSETS[i_index % len(DUE_OFFSETS)])
            session.add(
                Invoice(
                    tenant_id=tenant.id,
                    customer_id=customer.id,
                    invoice_no=f"INV-{1001 + i_index}",
                    issue_date=due_date - timedelta(days=30),
                    due_date=due_date,
                    total_sen=total_sen,
                    outstanding_sen=outstanding_sen,
                    status=status,
                )
            )
        session.flush()

        write_audit(
            session,
            tenant_id=tenant.id,
            actor_type=ACTOR_SYSTEM,
            action="SEED_CREATED",
            entity_type="tenant",
            entity_id=tenant.id,
            after={
                "tenant": tenant_name,
                "users": len(STAFF[t_index]),
                "customers": 25,
                "invoices": invoice_count,
                "note": "synthetic demo data, no real customers",
            },
        )

    session.commit()


def print_summary(session: Session) -> None:
    """Counts per table, the invoice status breakdown and the overdue buckets."""
    today = date.today()

    print("\nOrbit synthetic dataset")
    print("-" * 40)
    for label, model in (
        ("tenants", Tenant),
        ("users", User),
        ("customers", Customer),
        ("invoices", Invoice),
        ("audit_log", AuditLog),
    ):
        count = session.execute(select(func.count()).select_from(model)).scalar_one()
        print(f"  {label:<12}{count:>5}")

    print("\n  invoice status")
    for status, count in session.execute(
        select(Invoice.status, func.count()).group_by(Invoice.status).order_by(Invoice.status)
    ).all():
        print(f"    {status:<10}{count:>5}")

    print("\n  overdue buckets (unpaid invoices)")
    buckets = {"not yet due": 0, "1-6 days": 0, "7-13 days": 0, "14+ days": 0}
    for due_date in session.execute(
        select(Invoice.due_date).where(Invoice.outstanding_sen > 0)
    ).scalars():
        days = (today - due_date).days
        if days <= 0:
            buckets["not yet due"] += 1
        elif days < 7:
            buckets["1-6 days"] += 1
        elif days < 14:
            buckets["7-13 days"] += 1
        else:
            buckets["14+ days"] += 1
    for label, count in buckets.items():
        print(f"    {label:<12}{count:>5}")

    first = session.execute(select(Customer.name).order_by(Customer.id).limit(1)).scalar_one()
    print(f"\n  first customer: {first}\n")


def main() -> None:
    """Entry point for `python -m seed.generate_data`."""
    parser = argparse.ArgumentParser(description="Generate Orbit's synthetic demo data.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate every table first")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        already = session.execute(select(func.count()).select_from(Tenant)).scalar_one()
        if already and not args.reset:
            print("Data already present. Re-run with --reset to rebuild it.")
            return
        seed_all(session)
        print_summary(session)


if __name__ == "__main__":
    main()
