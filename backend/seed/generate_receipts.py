"""Generate the synthetic receipt images and their labels (docs/SPEC.md section 8.1).

    python -m seed.generate_receipts [--count 50]

Images land in seed/receipts/ (gitignored); seed/ground_truth.csv is committed and is
what MockExtractor reads, keyed by the SHA-256 of the PNG bytes.

Everything here is deterministic: one fixed random seed, and the receipts are built
from the invoices already in the database, so the demo really does reconcile. Dates
are anchored to today, exactly like seed/generate_data.py, so regenerating on another
day rewrites the images and the CSV together.

The labels assume each receipt is processed on its own against the seeded ledger.
Only the rows labelled DUPLICATE deliberately repeat an earlier transaction id.

No real bank, no real logo, no real customer: every name here is invented.
"""

import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from io import BytesIO
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Invoice, Tenant
from app.money import fmt_sen
from app.schemas import (
    DUPLICATE,
    EXACT_MATCH,
    LOW_CONFIDENCE,
    MULTI_INVOICE,
    NOT_A_RECEIPT,
    OVERPAYMENT,
    PARTIAL_PAYMENT,
    UNMATCHED,
)
from app.services.matching import AMOUNT_TOLERANCE_SEN

SEED = 20260124  # the same fixed seed as the data generator
TENANT_ID = 1  # the tenant we demo on
RECEIPTS_DIR = Path(__file__).resolve().parent / "receipts"
GROUND_TRUTH = Path(__file__).resolve().parent / "ground_truth.csv"

COLUMNS = [
    "filename",
    "image_sha256",
    "tenant_id",
    "customer_id",
    "invoice_no",
    "amount",
    "currency",
    "transaction_datetime",
    "payer_name",
    "payee_name",
    "channel",
    "bank_or_wallet",
    "reference_text",
    "transaction_id",
    "is_payment_receipt",
    "field_confidence_json",
    "expected_classification",
    "notes",
]

# (case slug, how many) - also the order the files are numbered in. The duplicates
# come after the exact matches because each one copies an earlier transaction id.
PLAN = [
    ("exact-match", 11),
    ("bm-exact-match", 4),
    ("partial-payment", 7),
    ("overpayment", 5),
    ("two-invoice", 4),
    ("duplicate", 3),
    ("cropped-ref", 4),
    ("blurry", 4),
    ("wrong-amount", 3),
    ("unknown-payer", 2),
    ("not-a-receipt", 3),
]

BANKS = [
    "Generic Bank Berhad",
    "NusaPay Wallet",
    "Bank Tiara Berhad",
    "SiriPay Wallet",
    "Teratai Bank Berhad",
]

# Fictional bank wording in English and Malay. Nothing here copies a real product.
LABELS = {
    "EN": {
        "status": "Transfer Successful",
        "stamp": "Date & time",
        "payer": "From",
        "payee": "To",
        "txn": "Transaction ID",
        "channel": "Type",
        "ref": "Reference",
        "footer": "Synthetic sample for the Orbit demo. Not a real bank document.",
        "resend": "Shared again from Gallery",
        "channels": ["Instant Transfer", "Online Transfer", "Wallet Transfer"],
    },
    "BM": {
        "status": "Pemindahan Berjaya",
        "stamp": "Tarikh & masa",
        "payer": "Daripada",
        "payee": "Kepada",
        "txn": "No. Transaksi",
        "channel": "Jenis",
        "ref": "Rujukan",
        "footer": "Contoh sintetik untuk demo Orbit. Bukan dokumen bank sebenar.",
        "resend": "Dikongsi semula dari Galeri",
        "channels": ["Pindahan Segera", "Pindahan Dalam Talian"],
    },
}

# Captions for the photos that are not receipts at all.
NOT_RECEIPT_CAPTIONS = [
    "Boss, stok paip 2 inci dah sampai warehouse",
    "Hi, confirm delivery tomorrow morning ya?",
    "Ni gambar lori masa sampai pagi tadi",
]

# Invented payers who are not in the customer book.
UNKNOWN_PAYERS = ["Chong Yuk Fatt Enterprise", "Hartanah Melur Resources"]

HIGH_CONFIDENCE = {"amount": 0.98, "date": 0.96, "payer_name": 0.94, "reference_text": 0.93}

WIDTH, HEIGHT = 560, 760
ROW_TOP, ROW_STEP = 226, 74
REFERENCE_ROW = 5  # the last row, so a crop above it loses the reference
PAGE_BG = (236, 238, 241)
CARD_BG = (255, 255, 255)
INK = (28, 32, 38)
MUTED = (118, 126, 138)
GOOD = (26, 127, 75)


@dataclass
class Target:
    """One unpaid invoice plus the customer facts a receipt needs."""

    invoice_no: str
    customer_id: int
    customer_name: str
    payer_name: str
    language: str
    outstanding_sen: int
    issue_date: date


@dataclass
class Receipt:
    """One labelled receipt: what the image shows and the row it becomes."""

    filename: str = ""
    case: str = ""
    expected: str = ""
    notes: str = ""
    language: str = "EN"
    customer_id: int | None = None
    invoice_nos: list[str] = field(default_factory=list)
    amount_sen: int | None = None
    stamp: datetime | None = None
    payer_name: str | None = None
    payee_name: str | None = None
    channel: str | None = None
    bank: str | None = None
    reference_text: str | None = None
    transaction_id: str | None = None
    is_payment_receipt: bool = True
    confidence: dict[str, float] = field(default_factory=lambda: dict(HIGH_CONFIDENCE))
    caption: str | None = None  # set only for the non-receipt photos
    blurry: bool = False
    crop_reference: bool = False
    resend: bool = False


# --- drawing -------------------------------------------------------------------


def _font(size: int) -> ImageFont.FreeTypeFont:
    """The PIL default font at a given size, so this runs on any machine."""
    return ImageFont.load_default(size=size)


def _bold(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill) -> None:
    """Fake a bold weight by drawing the same text twice, one pixel apart."""
    draw.text(xy, text, font=_font(size), fill=fill)
    draw.text((xy[0] + 1, xy[1]), text, font=_font(size), fill=fill)


def render(receipt: Receipt) -> bytes:
    """Draw one receipt (or non-receipt photo) and return the PNG bytes."""
    labels = LABELS[receipt.language]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAGE_BG)
    draw = ImageDraw.Draw(image)

    if receipt.caption is not None:
        # A plain photo with a caption: no amount, no fields, not a receipt.
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(203, 211, 218))
        _bold(draw, (40, 330), receipt.caption, 20, INK)
        draw.text((40, 380), labels["footer"], font=_font(13), fill=(90, 98, 108))
        return _png(image)

    draw.rounded_rectangle(
        (24, 24, WIDTH - 24, 700), radius=14, fill=CARD_BG, outline=(214, 219, 226)
    )
    _bold(draw, (48, 54), receipt.bank or "", 24, INK)
    draw.text((48, 96), labels["status"], font=_font(18), fill=GOOD)
    _bold(draw, (48, 132), fmt_sen(receipt.amount_sen or 0), 40, INK)
    draw.line((48, 200, WIDTH - 48, 200), fill=(226, 230, 236))

    rows = [
        (labels["stamp"], receipt.stamp.strftime("%d %b %Y, %H:%M") if receipt.stamp else "-"),
        (labels["payer"], receipt.payer_name or "-"),
        (labels["payee"], receipt.payee_name or "-"),
        (labels["txn"], receipt.transaction_id or "-"),
        (labels["channel"], receipt.channel or "-"),
        (labels["ref"], receipt.reference_text or "-"),
    ]
    for position, (label, value) in enumerate(rows):
        y = ROW_TOP + position * ROW_STEP
        draw.text((48, y), label, font=_font(15), fill=MUTED)
        draw.text((48, y + 22), value, font=_font(19), fill=INK)

    if receipt.resend:
        draw.text((48, 666), labels["resend"], font=_font(14), fill=MUTED)
    draw.text((48, 716), labels["footer"], font=_font(13), fill=(100, 108, 118))

    if receipt.crop_reference:
        image = image.crop((0, 0, WIDTH, ROW_TOP + REFERENCE_ROW * ROW_STEP - 6))
    if receipt.blurry:
        image = image.filter(ImageFilter.GaussianBlur(1.9))
        image = ImageEnhance.Contrast(image).enhance(0.5)
    return _png(image)


def _png(image: Image.Image) -> bytes:
    """PNG bytes for an image. No timestamp chunk, so the same picture hashes the same."""
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# --- choosing amounts and dates ------------------------------------------------


def _ambiguous(amount_sen: int, outstandings: list[int]) -> bool:
    """True if this amount would read as an exact match for one invoice or a combination."""
    if any(abs(amount_sen - value) <= AMOUNT_TOLERANCE_SEN for value in outstandings):
        return True
    unique = sorted(set(outstandings))
    return any(
        sum(combo) == amount_sen for size in (2, 3) for combo in combinations(unique, size)
    )


def _nudge(amount_sen: int, outstandings: list[int], step: int = 100) -> int:
    """Move an amount up in `step`s until it is nobody's exact balance."""
    while amount_sen <= 0 or _ambiguous(amount_sen, outstandings):
        amount_sen += step
    return amount_sen


def _stamp(index: int, repeats: int, issue_date: date, today: date) -> datetime:
    """A transaction time in the recent past, never before the invoice was issued.

    `repeats` spaces out receipts that share a customer and an amount, so the
    "same amount within 24 hours" duplicate rule only fires where we mean it to.
    """
    offset = (index * 3 + repeats * 3) % 10
    day = min(max(today - timedelta(days=offset), issue_date + timedelta(days=1)), today)
    return datetime.combine(day, time(9 + index % 11, (index * 7) % 60))


# --- building the set ----------------------------------------------------------


def load_targets(session: Session) -> tuple[str, list[Target]]:
    """The tenant's own name (the payee) and every unpaid invoice of theirs."""
    payee = session.execute(select(Tenant.name).where(Tenant.id == TENANT_ID)).scalar_one()
    invoices = (
        session.execute(
            select(Invoice)
            .where(Invoice.tenant_id == TENANT_ID, Invoice.outstanding_sen > 0)
            .order_by(Invoice.id)
        )
        .scalars()
        .all()
    )
    targets = [
        Target(
            invoice_no=invoice.invoice_no,
            customer_id=invoice.customer_id,
            customer_name=invoice.customer.name,
            # Customers write their nickname on the slip when they have one.
            payer_name=(invoice.customer.aliases_json or [invoice.customer.name])[0],
            language="BM" if invoice.customer.language == "BM" else "EN",
            outstanding_sen=invoice.outstanding_sen,
            issue_date=invoice.issue_date,
        )
        for invoice in invoices
    ]
    return payee, targets


def scaled_plan(count: int) -> list[tuple[str, int]]:
    """PLAN at its full 50, or scaled to another count with every case kept twice."""
    if count == 50:
        return list(PLAN)
    scaled = [(case, max(2, round(quantity * count / 50))) for case, quantity in PLAN]
    drift = count - sum(quantity for _, quantity in scaled)
    case, quantity = scaled[0]
    scaled[0] = (case, max(2, quantity + drift))  # soak the rounding up in the largest bucket
    return scaled


def build(session: Session, count: int) -> list[Receipt]:
    """Build the labelled receipt set: `count` receipts following PLAN's mix."""
    rng = random.Random(SEED)
    today = date.today()
    payee, targets = load_targets(session)
    if len(targets) < 10:
        raise SystemExit("No unpaid invoices for tenant 1. Run python -m seed.generate_data first.")

    by_customer: dict[int, list[Target]] = {}
    for target in targets:
        by_customer.setdefault(target.customer_id, []).append(target)
    all_outstandings = [t.outstanding_sen for t in targets]

    # Customers with exactly two unpaid invoices carry the two-invoice payments.
    pairs = [group for group in by_customer.values() if len(group) == 2][:4]
    paired = {group[0].customer_id for group in pairs}
    singles = [t for t in targets if t.customer_id not in paired]

    receipts: list[Receipt] = []
    seen: dict[tuple[int, int], int] = {}  # (customer, amount) -> how many already
    index = 0
    cursor = 0

    def add(receipt: Receipt, case: str) -> None:
        """Number the file and keep the receipt."""
        nonlocal index
        index += 1
        receipt.case = case
        receipt.filename = f"{index:03d}-{case}.png"
        receipts.append(receipt)

    def common(target: Target, amount_sen: int, reference: str, language: str) -> Receipt:
        """The fields every real receipt shares, with the date spaced out."""
        repeats = seen.get((target.customer_id, amount_sen), 0)
        seen[(target.customer_id, amount_sen)] = repeats + 1
        return Receipt(
            language=language,
            customer_id=target.customer_id,
            invoice_nos=[target.invoice_no],
            amount_sen=amount_sen,
            stamp=_stamp(index, repeats, target.issue_date, today),
            payer_name=target.payer_name,
            payee_name=payee,
            channel=rng.choice(LABELS[language]["channels"]),
            bank=rng.choice(BANKS),
            reference_text=reference,
            transaction_id=f"TX{rng.randrange(10**9, 10**10)}",
        )

    for case, quantity in scaled_plan(count):
        for _ in range(quantity):
            if case == "not-a-receipt":
                add(
                    Receipt(
                        expected=NOT_A_RECEIPT,
                        notes="photo with a caption, no payment on it",
                        caption=NOT_RECEIPT_CAPTIONS[index % len(NOT_RECEIPT_CAPTIONS)],
                        is_payment_receipt=False,
                        confidence={},
                    ),
                    case,
                )
                continue

            if case == "unknown-payer":
                stranger = UNKNOWN_PAYERS[index % len(UNKNOWN_PAYERS)]
                add(
                    Receipt(
                        expected=UNMATCHED,
                        notes=f"payer '{stranger}' is not in the customer book",
                        amount_sen=_nudge(125_000 + index * 1_300, all_outstandings, 700),
                        stamp=datetime.combine(today - timedelta(days=index % 5), time(11, 25)),
                        payer_name=stranger,
                        payee_name=payee,
                        channel="Instant Transfer",
                        bank=rng.choice(BANKS),
                        reference_text="TRANSFER",
                        transaction_id=f"TX{rng.randrange(10**9, 10**10)}",
                    ),
                    case,
                )
                continue

            if case == "duplicate":
                # Copy an earlier exact match whole: same invoice, amount and id.
                earlier = [r for r in receipts if r.case == "exact-match"]
                original = earlier[index % len(earlier)]
                copy = Receipt(**dict(original.__dict__))
                copy.expected = DUPLICATE
                copy.resend = True
                copy.notes = f"same transaction id as {original.filename}"
                add(copy, case)
                continue

            if case == "two-invoice":
                first, second = pairs[index % len(pairs)]
                amount = first.outstanding_sen + second.outstanding_sen
                receipt = common(
                    first, amount, f"{first.invoice_no} {second.invoice_no}", first.language
                )
                receipt.invoice_nos = [first.invoice_no, second.invoice_no]
                receipt.expected = MULTI_INVOICE
                receipt.notes = "one transfer settling both of the customer's invoices"
                add(receipt, case)
                continue

            target = singles[cursor % len(singles)]
            cursor += 1
            own = [t.outstanding_sen for t in by_customer[target.customer_id]]

            if case == "exact-match":
                receipt = common(target, target.outstanding_sen, target.invoice_no, "EN")
                receipt.expected = EXACT_MATCH
                receipt.notes = f"pays {target.invoice_no} in full, reference present"
            elif case == "bm-exact-match":
                receipt = common(
                    target, target.outstanding_sen, f"BAYARAN {target.invoice_no}", "BM"
                )
                receipt.expected = EXACT_MATCH
                receipt.notes = f"Malay-language receipt, pays {target.invoice_no} in full"
            elif case == "partial-payment":
                amount = _nudge((target.outstanding_sen // 2 // 100) * 100, own)
                receipt = common(target, amount, target.invoice_no, target.language)
                receipt.expected = PARTIAL_PAYMENT
                receipt.notes = f"part payment of {target.invoice_no}, a balance remains"
            elif case == "overpayment":
                amount = _nudge(target.outstanding_sen + 5_000, own)
                receipt = common(target, amount, target.invoice_no, target.language)
                receipt.expected = OVERPAYMENT
                receipt.notes = f"pays more than {target.invoice_no} is owed"
            elif case == "cropped-ref":
                receipt = common(target, target.outstanding_sen, "", target.language)
                receipt.crop_reference = True
                receipt.confidence = {**HIGH_CONFIDENCE, "reference_text": 0.31}
                receipt.expected = LOW_CONFIDENCE
                receipt.notes = "screenshot cut off above the reference line"
            elif case == "blurry":
                receipt = common(target, target.outstanding_sen, target.invoice_no, target.language)
                receipt.blurry = True
                receipt.confidence = {**HIGH_CONFIDENCE, "amount": 0.54, "date": 0.61}
                receipt.expected = LOW_CONFIDENCE
                receipt.notes = "blurred and low contrast, the amount is hard to read"
            elif case == "wrong-amount":
                amount = _nudge(target.outstanding_sen + 37_777, own + all_outstandings, 911)
                receipt = common(target, amount, "TRF OCT", target.language)
                receipt.expected = UNMATCHED
                receipt.notes = "amount matches no invoice and there is no reference"
            else:
                raise ValueError(f"unknown case {case}")

            add(receipt, case)

    return receipts


# --- writing -------------------------------------------------------------------


def write_all(receipts: list[Receipt]) -> None:
    """Write every PNG into seed/receipts/ and the labels into ground_truth.csv."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    for stale in RECEIPTS_DIR.glob("*.png"):
        stale.unlink()

    rows = []
    digests: dict[str, str] = {}
    for receipt in receipts:
        payload = render(receipt)
        digest = hashlib.sha256(payload).hexdigest()
        if digest in digests:
            # Two identical pictures would collide in the extractor's lookup table.
            raise SystemExit(f"{receipt.filename} is byte-identical to {digests[digest]}")
        digests[digest] = receipt.filename
        (RECEIPTS_DIR / receipt.filename).write_bytes(payload)
        rows.append(_row(receipt, digest))

    with GROUND_TRUTH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _row(receipt: Receipt, digest: str) -> dict[str, object]:
    """One ground_truth.csv row. The amount is in ringgit: it is what a model reads."""
    amount = ""
    if receipt.amount_sen is not None:
        amount = f"{receipt.amount_sen // 100}.{receipt.amount_sen % 100:02d}"
    return {
        "filename": receipt.filename,
        "image_sha256": digest,
        "tenant_id": TENANT_ID,
        "customer_id": receipt.customer_id or "",
        "invoice_no": "|".join(receipt.invoice_nos),  # pipe-separated for two-invoice payments
        "amount": amount,
        "currency": "MYR" if receipt.is_payment_receipt else "",
        "transaction_datetime": receipt.stamp.isoformat() if receipt.stamp else "",
        "payer_name": receipt.payer_name or "",
        "payee_name": receipt.payee_name or "",
        "channel": receipt.channel or "",
        "bank_or_wallet": receipt.bank or "",
        "reference_text": receipt.reference_text or "",
        "transaction_id": receipt.transaction_id or "",
        "is_payment_receipt": "true" if receipt.is_payment_receipt else "false",
        "field_confidence_json": json.dumps(receipt.confidence, separators=(",", ":")),
        "expected_classification": receipt.expected,
        "notes": receipt.notes,
    }


def print_summary(receipts: list[Receipt]) -> None:
    """How many of each expected classification were written."""
    counts: dict[str, int] = {}
    for receipt in receipts:
        counts[receipt.expected] = counts.get(receipt.expected, 0) + 1

    print(f"\nOrbit synthetic receipts -> {RECEIPTS_DIR}")
    print("-" * 46)
    for classification, count in sorted(counts.items()):
        print(f"  {classification:<18}{count:>4}")
    print("-" * 46)
    print(f"  {'total':<18}{len(receipts):>4}")
    print(f"  labels: {GROUND_TRUTH}\n")


def main() -> None:
    """Entry point for `python -m seed.generate_receipts`."""
    parser = argparse.ArgumentParser(description="Generate Orbit's synthetic receipt images.")
    parser.add_argument("--count", type=int, default=50, help="how many receipts (default 50)")
    args = parser.parse_args()
    if args.count < 22:
        raise SystemExit("--count must be at least 22 to cover every case twice")

    with SessionLocal() as session:
        receipts = build(session, args.count)
    write_all(receipts)
    print_summary(receipts)


if __name__ == "__main__":
    main()
