"""The eight verdicts an owner can be shown (docs/SPEC.md section 14 step 10).

Pure classification: no database, no AI, no generated prose. One test per
classification, plus the precedence rules that stop a wrong one being shown.
"""

from datetime import datetime, timedelta, timezone

from app.schemas import (
    DUPLICATE,
    EXACT_MATCH,
    LOW_CONFIDENCE,
    MULTI_INVOICE,
    NOT_A_RECEIPT,
    OVERPAYMENT,
    PARTIAL_PAYMENT,
    UNMATCHED,
    Allocation,
    Candidate,
    ExtractedFields,
    SignalHit,
)
from app.services.classify import LABEL_HUMAN, LABEL_LIKELY, LABEL_STRONG, classify

PAID_AT = datetime.now(timezone.utc) - timedelta(days=1)


def _receipt(**overrides) -> ExtractedFields:
    """A readable RM 850.00 receipt; overrides spoil one field."""
    fields = {
        "is_payment_receipt": True,
        "amount_sen": 85000,
        "transaction_datetime": PAID_AT,
        "payer_name": "Tan Ah Seng",
        "reference_text": "INV-1042",
        "field_confidence": {"amount": 0.98, "date": 0.95, "payer_name": 0.9},
    }
    fields.update(overrides)
    return ExtractedFields(**fields)


def _candidate(score: int = 100, outstanding_sen: int = 85000, no: str = "INV-1042") -> Candidate:
    """One scored invoice with a matched row and a missing row to cite."""
    return Candidate(
        invoice_id=1,
        invoice_no=no,
        outstanding_sen=outstanding_sen,
        score=score,
        signals=[
            SignalHit(
                name="amount",
                awarded=40,
                maximum=40,
                matched=True,
                detail="Amount RM 850.00 equals the outstanding balance",
            ),
            SignalHit(
                name="phone",
                awarded=0,
                maximum=10,
                matched=False,
                detail="No phone number on file to compare the sender against",
            ),
        ],
    )


def test_a_clean_full_payment_is_approved_as_an_exact_match():
    decision = classify(_receipt(), [_candidate()])
    assert decision.classification == EXACT_MATCH
    assert decision.confidence == 100
    assert decision.explanation["confidence_label"] == LABEL_STRONG
    assert decision.explanation["amount_display"] == "RM 850.00"
    assert decision.explanation["matched"]
    assert decision.explanation["next_step"]
    assert decision.allocations[0].amount_sen == 85000


def test_paying_less_than_the_invoice_is_a_part_payment_with_the_balance_stated():
    decision = classify(_receipt(amount_sen=40000), [_candidate(score=75)])
    assert decision.classification == PARTIAL_PAYMENT
    assert decision.confidence == 75
    assert decision.explanation["confidence_label"] == LABEL_LIKELY
    assert decision.explanation["amount_display"] == "RM 400.00"
    assert "RM 450.00" in decision.explanation["next_step"]
    assert decision.allocations[0].amount_sen == 40000


def test_paying_more_than_the_invoice_is_an_overpayment_and_orbit_moves_no_money():
    decision = classify(_receipt(amount_sen=120000), [_candidate(score=75)])
    assert decision.classification == OVERPAYMENT
    assert decision.explanation["amount_display"] == "RM 1,200.00"
    assert "RM 350.00" in decision.explanation["headline"]
    assert "does not move any money" in decision.explanation["next_step"]
    # Only what was owing is allocated; the excess is the owner's decision.
    assert decision.allocations[0].amount_sen == 85000


def test_one_transfer_covering_two_invoices_is_a_multi_invoice_split():
    allocations = [
        Allocation(invoice_id=1, invoice_no="INV-3001", amount_sen=30000),
        Allocation(invoice_id=2, invoice_no="INV-3002", amount_sen=55000),
    ]
    decision = classify(_receipt(), [_candidate(score=75)], multi_allocations=allocations)
    assert decision.classification == MULTI_INVOICE
    assert decision.confidence == 75
    assert [a.invoice_no for a in decision.allocations] == ["INV-3001", "INV-3002"]
    assert "INV-3001, INV-3002" in decision.explanation["headline"]
    # A split is never auto-approved; the owner confirms or changes it.
    assert decision.explanation["confidence_label"] == LABEL_LIKELY
    assert "Confirm the split" in decision.explanation["next_step"]


def test_the_same_receipt_sent_twice_is_flagged_as_already_recorded():
    decision = classify(_receipt(), [_candidate()], duplicate_payment_id=7)
    assert decision.classification == DUPLICATE
    assert decision.explanation["confidence_label"] == LABEL_HUMAN
    assert "Already recorded" in decision.explanation["headline"]
    assert "RM 850.00" in decision.explanation["headline"]


def test_a_payment_with_no_plausible_invoice_is_left_unmatched_for_a_human():
    # A score below THRESHOLD_CANDIDATE is not a candidate at all.
    decision = classify(_receipt(), [_candidate(score=20)])
    assert decision.classification == UNMATCHED
    assert decision.confidence == 0
    assert decision.explanation["confidence_label"] == LABEL_HUMAN
    assert "no matching invoice found" in decision.explanation["headline"]


def test_a_blurry_receipt_is_sent_to_a_human_instead_of_being_guessed():
    decision = classify(
        _receipt(field_confidence={"amount": 0.4, "date": 0.9}), [_candidate()]
    )
    assert decision.classification == LOW_CONFIDENCE
    assert decision.explanation["confidence_label"] == LABEL_HUMAN
    assert "hard to read" in " ".join(decision.explanation["missing"])


def test_a_photo_that_is_not_a_receipt_records_nothing():
    decision = classify(
        ExtractedFields(is_payment_receipt=False, notes="a photo of a cat"), []
    )
    assert decision.classification == NOT_A_RECEIPT
    assert decision.confidence == 0
    assert decision.allocations == []
    assert "does not look like a payment receipt" in decision.explanation["headline"]


def test_a_missing_reference_number_is_named_in_the_explanation():
    decision = classify(_receipt(reference_text=None), [_candidate()])
    assert "Reference number not found, please confirm" in decision.explanation["missing"]


def test_a_duplicate_beats_an_otherwise_perfect_match():
    # Same inputs as the exact-match case, plus a prior payment id.
    assert classify(_receipt(), [_candidate()]).classification == EXACT_MATCH
    decision = classify(_receipt(), [_candidate()], duplicate_payment_id=7)
    assert decision.classification == DUPLICATE


def test_not_a_receipt_beats_every_other_verdict():
    decision = classify(
        ExtractedFields(is_payment_receipt=False, amount_sen=85000),
        [_candidate()],
        duplicate_payment_id=7,
        multi_allocations=[
            Allocation(invoice_id=1, invoice_no="INV-3001", amount_sen=30000),
            Allocation(invoice_id=2, invoice_no="INV-3002", amount_sen=55000),
        ],
    )
    assert decision.classification == NOT_A_RECEIPT
    assert decision.confidence == 0
    assert decision.allocations == []
