"""Deterministic match scorecard (docs/SPEC.md section 7.2).

Pure functions: no database, no session, no AI. Given what was read off a
receipt and a list of open invoices, award weighted signals and return
candidates a human can check line by line.
"""

import hmac
import re
from datetime import datetime, timezone
from itertools import combinations

from rapidfuzz import fuzz

from app.money import fmt_sen
from app.schemas import (
    DEFAULT_WEIGHTS,
    SIGNAL_AMOUNT,
    SIGNAL_DATE,
    SIGNAL_PAYER_NAME,
    SIGNAL_PHONE,
    SIGNAL_REFERENCE,
    SIGNAL_SOLE_INVOICE,
    Allocation,
    Candidate,
    CustomerView,
    ExtractedFields,
    InvoiceView,
    SignalHit,
)

# An amount within this many sen of the outstanding balance is a near match.
AMOUNT_TOLERANCE_SEN = 5
AMOUNT_NEAR_AWARD = 35

# Below this similarity the payer name tells us nothing useful.
NAME_SIMILARITY_FLOOR = 0.6

_NON_REF = re.compile(r"[^A-Z0-9]+")
_COMPANY_SUFFIXES = ("SDN BHD", "BHD", "ENTERPRISES", "ENTERPRISE", "TRADING")


def normalise_ref(text: str | None) -> str:
    """Uppercase and strip everything that is not a letter or a digit."""
    if not text:
        return ""
    return _NON_REF.sub("", text.upper())


def normalise_name(name: str | None) -> str:
    """Uppercase, collapse whitespace and drop common company suffixes."""
    if not name:
        return ""
    cleaned = " ".join(re.sub(r"[^A-Z0-9 ]+", " ", name.upper()).split())
    for suffix in _COMPANY_SUFFIXES:
        if cleaned == suffix:
            return ""
        if cleaned.endswith(" " + suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return " ".join(cleaned.split())


def name_similarity(payer: str | None, customer_name: str, aliases: list[str]) -> float:
    """Best token_set_ratio (0.0-1.0) of the payer against the name and every alias."""
    left = normalise_name(payer)
    if not left:
        return 0.0
    best = 0.0
    for candidate in [customer_name, *aliases]:
        right = normalise_name(candidate)
        if right:
            best = max(best, fuzz.token_set_ratio(left, right) / 100.0)
    return best


def _amount_signal(extracted: ExtractedFields, invoice: InvoiceView, weight: int) -> SignalHit:
    paid = extracted.amount_sen or 0
    outstanding = invoice.outstanding_sen
    delta = abs(paid - outstanding)
    if delta == 0:
        return SignalHit(
            name=SIGNAL_AMOUNT,
            awarded=weight,
            maximum=weight,
            matched=True,
            detail=f"Amount {fmt_sen(paid)} equals the outstanding balance",
        )
    if delta <= AMOUNT_TOLERANCE_SEN:
        return SignalHit(
            name=SIGNAL_AMOUNT,
            awarded=min(AMOUNT_NEAR_AWARD, weight),
            maximum=weight,
            matched=True,
            detail=(
                f"Amount {fmt_sen(paid)} is within {delta} sen of the "
                f"outstanding {fmt_sen(outstanding)}"
            ),
        )
    if paid < outstanding:
        # Instalment guessing is out of scope for the MVP; a human decides.
        detail = (
            f"Amount {fmt_sen(paid)} is below the outstanding {fmt_sen(outstanding)}, "
            "possibly a part payment, not scored"
        )
    else:
        detail = f"Amount {fmt_sen(paid)} is above the outstanding {fmt_sen(outstanding)}"
    return SignalHit(name=SIGNAL_AMOUNT, awarded=0, maximum=weight, matched=False, detail=detail)


def _reference_signal(extracted: ExtractedFields, invoice: InvoiceView, weight: int) -> SignalHit:
    ref = normalise_ref(extracted.reference_text)
    target = normalise_ref(invoice.invoice_no)
    if not ref:
        detail = "No reference number on the receipt"
    elif target and target in ref:
        return SignalHit(
            name=SIGNAL_REFERENCE,
            awarded=weight,
            maximum=weight,
            matched=True,
            detail=f"Reference mentions invoice {invoice.invoice_no}",
        )
    else:
        detail = f"Reference does not mention invoice {invoice.invoice_no}"
    return SignalHit(name=SIGNAL_REFERENCE, awarded=0, maximum=weight, matched=False, detail=detail)


def _payer_name_signal(
    extracted: ExtractedFields, customer: CustomerView | None, weight: int
) -> SignalHit:
    if customer is None:
        detail = "No customer to compare the payer name against"
    elif not extracted.payer_name:
        detail = "No payer name on the receipt"
    else:
        score = name_similarity(extracted.payer_name, customer.name, customer.aliases)
        percent = round(score * 100)
        if score > NAME_SIMILARITY_FLOOR:
            return SignalHit(
                name=SIGNAL_PAYER_NAME,
                awarded=round(score * weight),
                maximum=weight,
                matched=True,
                detail=f"Payer '{extracted.payer_name}' is {percent}% similar to {customer.name}",
            )
        detail = f"Payer '{extracted.payer_name}' does not look like {customer.name}"
    return SignalHit(
        name=SIGNAL_PAYER_NAME, awarded=0, maximum=weight, matched=False, detail=detail
    )


def _phone_signal(
    sender_phone_hmac: str | None, customer: CustomerView | None, weight: int
) -> SignalHit:
    on_file = customer.phone_hmac if customer else None
    if not sender_phone_hmac or not on_file:
        detail = "No phone number on file to compare the sender against"
    elif hmac.compare_digest(sender_phone_hmac, on_file):
        return SignalHit(
            name=SIGNAL_PHONE,
            awarded=weight,
            maximum=weight,
            matched=True,
            detail="Sender's number matches the number on file for this customer",
        )
    else:
        detail = "Sender's number is not the one on file for this customer"
    return SignalHit(name=SIGNAL_PHONE, awarded=0, maximum=weight, matched=False, detail=detail)


def _date_signal(extracted: ExtractedFields, invoice: InvoiceView, weight: int) -> SignalHit:
    stamp = extracted.transaction_datetime
    if stamp is None:
        detail = "No transaction date on the receipt"
    else:
        paid_on = stamp.date()
        today = datetime.now(timezone.utc).date()
        if paid_on < invoice.issue_date:
            detail = (
                f"Paid {paid_on}, before invoice {invoice.invoice_no} "
                f"was issued on {invoice.issue_date}"
            )
        elif paid_on > today:
            detail = f"Transaction date {paid_on} is in the future"
        else:
            return SignalHit(
                name=SIGNAL_DATE,
                awarded=weight,
                maximum=weight,
                matched=True,
                detail=f"Paid {paid_on}, on or after the invoice date {invoice.issue_date}",
            )
    return SignalHit(name=SIGNAL_DATE, awarded=0, maximum=weight, matched=False, detail=detail)


def _sole_invoice_signal(open_invoice_count: int, weight: int) -> SignalHit:
    if open_invoice_count == 1:
        return SignalHit(
            name=SIGNAL_SOLE_INVOICE,
            awarded=weight,
            maximum=weight,
            matched=True,
            detail="This is the customer's only open invoice",
        )
    return SignalHit(
        name=SIGNAL_SOLE_INVOICE,
        awarded=0,
        maximum=weight,
        matched=False,
        detail=f"The customer has {open_invoice_count} open invoices",
    )


def score_invoice(
    extracted: ExtractedFields,
    invoice: InvoiceView,
    customer: CustomerView | None = None,
    *,
    weights: dict[str, int] | None = None,
    sender_phone_hmac: str | None = None,
    open_invoice_count: int = 1,
) -> Candidate:
    """Score one invoice against one receipt and return the whole scorecard."""
    w = weights or DEFAULT_WEIGHTS
    builders = {
        SIGNAL_AMOUNT: lambda weight: _amount_signal(extracted, invoice, weight),
        SIGNAL_REFERENCE: lambda weight: _reference_signal(extracted, invoice, weight),
        SIGNAL_PAYER_NAME: lambda weight: _payer_name_signal(extracted, customer, weight),
        SIGNAL_PHONE: lambda weight: _phone_signal(sender_phone_hmac, customer, weight),
        SIGNAL_DATE: lambda weight: _date_signal(extracted, invoice, weight),
        SIGNAL_SOLE_INVOICE: lambda weight: _sole_invoice_signal(open_invoice_count, weight),
    }
    # DEFAULT_WEIGHTS fixes the row order, so the explanation reads the same every time.
    signals = [builders[name](w.get(name, 0)) for name in DEFAULT_WEIGHTS]
    score = max(0, min(100, sum(s.awarded for s in signals)))
    return Candidate(
        invoice_id=invoice.id,
        invoice_no=invoice.invoice_no,
        outstanding_sen=invoice.outstanding_sen,
        score=score,
        signals=signals,
    )


def score_candidates(
    extracted: ExtractedFields,
    invoices: list[InvoiceView],
    customer: CustomerView | None = None,
    *,
    weights: dict[str, int] | None = None,
    sender_phone_hmac: str | None = None,
) -> list[Candidate]:
    """Score every invoice, best first; a tie goes to the oldest due date."""
    due_dates = {inv.id: inv.due_date for inv in invoices}
    candidates = [
        score_invoice(
            extracted,
            invoice,
            customer,
            weights=weights,
            sender_phone_hmac=sender_phone_hmac,
            open_invoice_count=len(invoices),
        )
        for invoice in invoices
    ]
    candidates.sort(key=lambda c: (-c.score, due_dates[c.invoice_id], c.invoice_no))
    return candidates


def find_multi_invoice_combination(
    extracted: ExtractedFields,
    invoices: list[InvoiceView],
    *,
    max_invoices: int = 3,
) -> list[Allocation]:
    """Find 2..max_invoices invoices whose outstanding sums exactly to the amount paid."""
    target = extracted.amount_sen or 0
    if target <= 0 or len(invoices) < 2:
        return []
    ordered = sorted(invoices, key=lambda inv: (inv.due_date, inv.invoice_no))
    for size in range(2, min(max_invoices, len(ordered)) + 1):
        for combo in combinations(ordered, size):
            if sum(inv.outstanding_sen for inv in combo) == target:
                return [
                    Allocation(
                        invoice_id=inv.id,
                        invoice_no=inv.invoice_no,
                        amount_sen=inv.outstanding_sen,
                    )
                    for inv in combo
                ]
    return []
