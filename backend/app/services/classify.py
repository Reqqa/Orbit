"""Deterministic classification and templated explanation (docs/SPEC.md section 7.3).

Pure functions: no database, no session, no model-generated prose. Duplicate
detection and the multi-invoice search belong to the caller and arrive as
arguments, so the rules here are trivially testable.
"""

from app.money import fmt_sen
from app.schemas import (
    DUPLICATE,
    EXACT_MATCH,
    LOW_CONFIDENCE,
    MIN_FIELD_CONFIDENCE,
    MULTI_INVOICE,
    NOT_A_RECEIPT,
    OVERPAYMENT,
    PARTIAL_PAYMENT,
    THRESHOLD_CANDIDATE,
    THRESHOLD_LIKELY,
    THRESHOLD_STRONG,
    UNMATCHED,
    Allocation,
    Candidate,
    Decision,
    ExtractedFields,
)

# Shown to a shop owner, so the wording avoids the word "confidence".
LABEL_STRONG = "Strong match"
LABEL_LIKELY = "Likely, please check"
LABEL_HUMAN = "Needs human"

# These never get an encouraging label, however high the score is.
_ALWAYS_HUMAN = (NOT_A_RECEIPT, DUPLICATE, UNMATCHED, LOW_CONFIDENCE)


def classify(
    extracted: ExtractedFields,
    candidates: list[Candidate],
    *,
    duplicate_payment_id: int | None = None,
    multi_allocations: list[Allocation] | None = None,
) -> Decision:
    """Pick one classification for a receipt and explain it. Precedence matters."""
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = ranked[0] if ranked and ranked[0].score >= THRESHOLD_CANDIDATE else None
    confidence = best.score if best else 0
    amount_sen = extracted.amount_sen or 0

    classification = None
    allocations: list[Allocation] = []

    if not extracted.is_payment_receipt:
        classification, confidence = NOT_A_RECEIPT, 0
    elif duplicate_payment_id is not None:
        classification = DUPLICATE
    elif extracted.lowest_key_confidence < MIN_FIELD_CONFIDENCE:
        classification = LOW_CONFIDENCE
    elif multi_allocations and len(multi_allocations) >= 2:
        classification, allocations = MULTI_INVOICE, list(multi_allocations)
    elif best is None:
        classification, confidence = UNMATCHED, 0
    elif best.score >= THRESHOLD_STRONG and amount_sen == best.outstanding_sen:
        classification = EXACT_MATCH
    elif amount_sen > best.outstanding_sen:
        classification = OVERPAYMENT
    elif amount_sen < best.outstanding_sen:
        classification = PARTIAL_PAYMENT
    else:
        classification = LOW_CONFIDENCE

    if best is not None and classification in (EXACT_MATCH, PARTIAL_PAYMENT, OVERPAYMENT):
        allocations = [
            Allocation(
                invoice_id=best.invoice_id,
                invoice_no=best.invoice_no,
                amount_sen=min(amount_sen, best.outstanding_sen),
            )
        ]

    return Decision(
        classification=classification,
        confidence=confidence,
        candidates=ranked,
        allocations=allocations,
        explanation=build_explanation(classification, extracted, ranked, allocations),
    )


def build_explanation(
    classification: str,
    extracted: ExtractedFields,
    candidates: list[Candidate],
    allocations: list[Allocation],
) -> dict:
    """Build the owner-facing explanation from templates only (section 5.1 step 6)."""
    amount_sen = extracted.amount_sen or 0
    amount_display = fmt_sen(amount_sen)
    best = candidates[0] if candidates else None
    score = best.score if best else 0

    matched = [s.detail for s in best.matched_signals] if best else []
    missing = _missing_lines(extracted, best)

    headline, next_step = _headline_and_next_step(
        classification, amount_display, amount_sen, best, allocations
    )

    return {
        "headline": headline,
        "confidence_label": _label(classification, score),
        "matched": matched,
        "missing": missing,
        "next_step": next_step,
        "amount_display": amount_display,
    }


def _label(classification: str, score: int) -> str:
    """Three plain labels. Exceptions always point at a person."""
    if classification in _ALWAYS_HUMAN:
        return LABEL_HUMAN
    if classification == EXACT_MATCH and score >= THRESHOLD_STRONG:
        return LABEL_STRONG
    if score >= THRESHOLD_LIKELY:
        return LABEL_LIKELY
    return LABEL_HUMAN


def _missing_lines(extracted: ExtractedFields, best: Candidate | None) -> list[str]:
    """What we could not confirm, written as a request to the human."""
    lines = [s.detail for s in best.missing_signals] if best else []
    if not extracted.reference_text:
        lines.append("Reference number not found, please confirm")
    if extracted.transaction_datetime is None:
        lines.append("Payment date not readable, please check the receipt")
    if not extracted.payer_name:
        lines.append("Payer name not readable, please confirm who paid")
    if extracted.lowest_key_confidence < MIN_FIELD_CONFIDENCE:
        lines.append("Some details on the image are hard to read, please verify them")
    return lines


def _headline_and_next_step(
    classification: str,
    amount_display: str,
    amount_sen: int,
    best: Candidate | None,
    allocations: list[Allocation],
) -> tuple[str, str]:
    """One templated headline and one plain next step per classification."""
    invoice_no = best.invoice_no if best else None

    if classification == NOT_A_RECEIPT:
        return (
            "This image does not look like a payment receipt",
            "Nothing was recorded. Ask the customer to send the payment receipt again.",
        )

    if classification == DUPLICATE:
        return (
            f"Already recorded: {amount_display}",
            "This payment looks like one you already have. Check it before recording it twice.",
        )

    if classification == MULTI_INVOICE:
        listed = ", ".join(a.invoice_no for a in allocations)
        return (
            f"{amount_display} covers {len(allocations)} invoices: {listed}",
            "We suggest paying off the oldest invoices first. Confirm the split or change it.",
        )

    if classification == UNMATCHED:
        return (
            f"{amount_display} received, no matching invoice found",
            "Please pick the customer and invoice this payment belongs to.",
        )

    if classification == EXACT_MATCH:
        return (
            f"Matches {invoice_no}, {amount_display}",
            f"Everything matches {invoice_no}. Approve to record the payment.",
        )

    if classification == PARTIAL_PAYMENT:
        remaining = fmt_sen(best.outstanding_sen - amount_sen) if best else amount_display
        return (
            f"Part payment of {amount_display} for {invoice_no}",
            f"Approve to record it as a part payment. {remaining} will still be owing on {invoice_no}.",
        )

    if classification == OVERPAYMENT:
        excess = fmt_sen(amount_sen - best.outstanding_sen) if best else amount_display
        return (
            f"{amount_display} for {invoice_no} is {excess} more than owing",
            f"You decide what to do with the extra {excess}: keep it as credit for the customer, "
            "or note a refund. Orbit does not move any money.",
        )

    # LOW_CONFIDENCE
    target = f" against {invoice_no}" if invoice_no else ""
    return (
        f"{amount_display} needs checking by eye{target}",
        "Open the receipt image and compare it with the details we read before approving.",
    )
