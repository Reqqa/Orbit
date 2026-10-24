"""The scorecard a shop owner is asked to trust (docs/SPEC.md section 14 step 9).

Pure scoring: no database, no session, no AI. Each test is one business case a
judge can read off the name.
"""

from datetime import date, datetime, timedelta, timezone

from app.schemas import (
    DEFAULT_WEIGHTS,
    SIGNAL_AMOUNT,
    SIGNAL_DATE,
    SIGNAL_PAYER_NAME,
    SIGNAL_PHONE,
    SIGNAL_REFERENCE,
    THRESHOLD_STRONG,
    CustomerView,
    ExtractedFields,
    InvoiceView,
)
from app.services.matching import (
    find_multi_invoice_combination,
    name_similarity,
    normalise_ref,
    score_candidates,
    score_invoice,
)

TODAY = date.today()
ISSUED = TODAY - timedelta(days=30)
DUE = TODAY - timedelta(days=5)
PAID_AT = datetime.now(timezone.utc) - timedelta(days=1)

CUSTOMER = CustomerView(
    id=1,
    name="Tan Ah Seng Enterprise",
    aliases=["Ah Seng Hardware"],
    phone_hmac="hmac-of-60123456789",
)


def _invoice(
    invoice_id: int = 1,
    invoice_no: str = "INV-1042",
    outstanding_sen: int = 85000,
    due_date: date = DUE,
) -> InvoiceView:
    """An open invoice for RM 850.00 unless the test says otherwise."""
    return InvoiceView(
        id=invoice_id,
        invoice_no=invoice_no,
        issue_date=ISSUED,
        due_date=due_date,
        total_sen=outstanding_sen,
        outstanding_sen=outstanding_sen,
    )


def _receipt(**overrides) -> ExtractedFields:
    """A clean receipt that pays INV-1042 in full; overrides spoil one field."""
    fields = {
        "is_payment_receipt": True,
        "amount_sen": 85000,
        "transaction_datetime": PAID_AT,
        "payer_name": "Tan Ah Seng",
        "reference_text": "Payment for INV-1042",
    }
    fields.update(overrides)
    return ExtractedFields(**fields)


def _signal(candidate, name):
    """The one scorecard row with this signal name."""
    return next(s for s in candidate.signals if s.name == name)


def test_a_clean_receipt_quoting_the_invoice_number_is_a_strong_match():
    candidate = score_invoice(
        _receipt(),
        _invoice(),
        CUSTOMER,
        sender_phone_hmac=CUSTOMER.phone_hmac,
        open_invoice_count=1,
    )
    assert candidate.score >= THRESHOLD_STRONG
    assert candidate.score == 100
    assert _signal(candidate, SIGNAL_AMOUNT).awarded == DEFAULT_WEIGHTS[SIGNAL_AMOUNT]
    assert _signal(candidate, SIGNAL_REFERENCE).awarded == DEFAULT_WEIGHTS[SIGNAL_REFERENCE]


def test_a_part_payment_keeps_every_other_signal_but_wins_no_amount_points():
    candidate = score_invoice(
        _receipt(amount_sen=40000),
        _invoice(),
        CUSTOMER,
        sender_phone_hmac=CUSTOMER.phone_hmac,
        open_invoice_count=1,
    )
    amount = _signal(candidate, SIGNAL_AMOUNT)
    assert amount.awarded == 0
    assert not amount.matched
    assert "below" in amount.detail
    # Everything except the 40 amount points still scores.
    assert candidate.score == 100 - DEFAULT_WEIGHTS[SIGNAL_AMOUNT]


def test_an_overpayment_also_wins_no_amount_points():
    candidate = score_invoice(
        _receipt(amount_sen=120000),
        _invoice(),
        CUSTOMER,
        sender_phone_hmac=CUSTOMER.phone_hmac,
        open_invoice_count=1,
    )
    amount = _signal(candidate, SIGNAL_AMOUNT)
    assert amount.awarded == 0
    assert "above" in amount.detail
    assert candidate.score == 100 - DEFAULT_WEIGHTS[SIGNAL_AMOUNT]


def test_customers_may_write_the_invoice_number_any_way_they_like():
    assert normalise_ref("inv 1042") == normalise_ref("INV-1042") == normalise_ref("inv1042")
    for written in ("inv 1042", "INV-1042", "inv1042", "paid inv/1042 thanks"):
        candidate = score_invoice(_receipt(reference_text=written), _invoice(), CUSTOMER)
        reference = _signal(candidate, SIGNAL_REFERENCE)
        assert reference.matched, written
        assert reference.awarded == DEFAULT_WEIGHTS[SIGNAL_REFERENCE]


def test_a_payer_who_pays_under_a_nickname_is_still_recognised():
    customer = CustomerView(id=2, name="Golden Dragon Hardware", aliases=["Tan Ah Seng Enterprise"])
    assert name_similarity("Ah Seng", customer.name, customer.aliases) > 0.6
    assert name_similarity("Siti Nurhaliza", customer.name, customer.aliases) < 0.6

    hit = _signal(
        score_invoice(_receipt(payer_name="Ah Seng"), _invoice(), customer), SIGNAL_PAYER_NAME
    )
    assert hit.matched
    assert hit.awarded == DEFAULT_WEIGHTS[SIGNAL_PAYER_NAME]

    miss = _signal(
        score_invoice(_receipt(payer_name="Siti Nurhaliza"), _invoice(), customer),
        SIGNAL_PAYER_NAME,
    )
    assert not miss.matched
    assert miss.awarded == 0


def test_sending_from_the_number_on_file_is_worth_points_and_another_number_is_not():
    mine = _signal(
        score_invoice(_receipt(), _invoice(), CUSTOMER, sender_phone_hmac=CUSTOMER.phone_hmac),
        SIGNAL_PHONE,
    )
    assert mine.matched
    assert mine.awarded == DEFAULT_WEIGHTS[SIGNAL_PHONE]

    stranger = _signal(
        score_invoice(_receipt(), _invoice(), CUSTOMER, sender_phone_hmac="hmac-of-somebody-else"),
        SIGNAL_PHONE,
    )
    assert not stranger.matched
    assert stranger.awarded == 0


def test_a_receipt_dated_in_the_future_loses_the_date_points():
    future = datetime.now(timezone.utc) + timedelta(days=3)
    candidate = score_invoice(_receipt(transaction_datetime=future), _invoice(), CUSTOMER)
    hit = _signal(candidate, SIGNAL_DATE)
    assert not hit.matched
    assert hit.awarded == 0
    assert "future" in hit.detail


def test_the_invoice_named_on_the_receipt_is_ranked_first():
    invoices = [
        _invoice(1, "INV-1001", 85000, TODAY - timedelta(days=20)),
        _invoice(2, "INV-1042", 85000, TODAY),
    ]
    ranked = score_candidates(_receipt(), invoices, CUSTOMER)
    assert [c.invoice_no for c in ranked] == ["INV-1042", "INV-1001"]
    assert ranked[0].score > ranked[1].score


def test_when_two_invoices_score_the_same_the_oldest_due_date_goes_first():
    # No reference and no payer name, so the two invoices are indistinguishable.
    receipt = _receipt(reference_text=None, payer_name=None)
    invoices = [
        _invoice(1, "INV-2000", 85000, TODAY),
        _invoice(2, "INV-2001", 85000, TODAY - timedelta(days=14)),
    ]
    ranked = score_candidates(receipt, invoices, CUSTOMER)
    assert ranked[0].score == ranked[1].score
    assert ranked[0].invoice_no == "INV-2001"


def test_one_transfer_can_settle_two_invoices_exactly():
    invoices = [
        _invoice(1, "INV-3001", 30000, TODAY - timedelta(days=20)),
        _invoice(2, "INV-3002", 55000, TODAY - timedelta(days=10)),
        _invoice(3, "INV-3003", 99900, TODAY),
    ]
    allocations = find_multi_invoice_combination(_receipt(amount_sen=85000), invoices)
    assert [a.invoice_no for a in allocations] == ["INV-3001", "INV-3002"]
    assert sum(a.amount_sen for a in allocations) == 85000


def test_no_combination_of_invoices_is_invented_when_the_sum_does_not_land():
    invoices = [
        _invoice(1, "INV-3001", 30000),
        _invoice(2, "INV-3002", 55000),
    ]
    assert find_multi_invoice_combination(_receipt(amount_sen=12345), invoices) == []
