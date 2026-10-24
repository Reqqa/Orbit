"""Shared contracts between extraction, matching, classification and the API.

These are plain data objects with no database access, so the matching and
classification engines stay pure and testable (docs/SPEC.md sections 7.1-7.3).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.money import to_sen

# --- Classifications (docs/SPEC.md section 7.3) ---
EXACT_MATCH = "EXACT_MATCH"
PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
OVERPAYMENT = "OVERPAYMENT"
MULTI_INVOICE = "MULTI_INVOICE"
DUPLICATE = "DUPLICATE"
UNMATCHED = "UNMATCHED"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
NOT_A_RECEIPT = "NOT_A_RECEIPT"

CLASSIFICATIONS = (
    EXACT_MATCH,
    PARTIAL_PAYMENT,
    OVERPAYMENT,
    MULTI_INVOICE,
    DUPLICATE,
    UNMATCHED,
    LOW_CONFIDENCE,
    NOT_A_RECEIPT,
)

# Anything other than a clean exact match is an exception and always goes to the Owner.
EXCEPTION_CLASSIFICATIONS = (
    OVERPAYMENT,
    MULTI_INVOICE,
    DUPLICATE,
    UNMATCHED,
    LOW_CONFIDENCE,
    NOT_A_RECEIPT,
)

# --- Match signals and their maximum weights (docs/SPEC.md section 7.2) ---
SIGNAL_AMOUNT = "amount"
SIGNAL_REFERENCE = "reference"
SIGNAL_PAYER_NAME = "payer_name"
SIGNAL_PHONE = "phone"
SIGNAL_DATE = "date"
SIGNAL_SOLE_INVOICE = "sole_invoice"

DEFAULT_WEIGHTS: dict[str, int] = {
    SIGNAL_AMOUNT: 40,
    SIGNAL_REFERENCE: 25,
    SIGNAL_PAYER_NAME: 15,
    SIGNAL_PHONE: 10,
    SIGNAL_DATE: 5,
    SIGNAL_SOLE_INVOICE: 5,
}

# Confidence thresholds, configurable per tenant via settings_json.
THRESHOLD_STRONG = 90  # >= is "Strong match"
THRESHOLD_LIKELY = 70  # >= is "Likely, please check"
THRESHOLD_CANDIDATE = 40  # below this an invoice is not a candidate at all
MIN_FIELD_CONFIDENCE = 0.7  # below this on a key field, route to a human


class ExtractedFields(BaseModel):
    """What the vision model is allowed to tell us (docs/SPEC.md section 7.1).

    The model only reads. It never decides a match, a classification or an approval.
    """

    model_config = ConfigDict(extra="ignore")

    is_payment_receipt: bool
    amount: Decimal | None = None
    amount_sen: int | None = None
    currency: str = "MYR"
    transaction_datetime: datetime | None = None
    payer_name: str | None = None
    payee_name: str | None = None
    channel: str | None = None
    bank_or_wallet: str | None = None
    reference_text: str | None = None
    transaction_id: str | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="after")
    def _derive_amount_sen(self) -> "ExtractedFields":
        if self.amount_sen is None and self.amount is not None:
            object.__setattr__(self, "amount_sen", to_sen(self.amount))
        if self.amount_sen is not None and self.amount_sen <= 0:
            raise ValueError("an amount on a receipt must be positive")
        if self.is_payment_receipt and self.amount_sen is None:
            # A receipt with no readable amount is not fatal, it is a human review.
            # Marking the confidence here is what routes it to LOW_CONFIDENCE.
            self.field_confidence.setdefault("amount", 0.0)
        return self

    @property
    def usable_for_matching(self) -> bool:
        """False when there is nothing to score an invoice against."""
        return bool(self.is_payment_receipt and self.amount_sen)

    @property
    def lowest_key_confidence(self) -> float:
        """Lowest confidence among the fields a match depends on."""
        keys = ("amount", "date", "payer_name", "reference_text")
        scores = [self.field_confidence.get(k) for k in keys]
        present = [s for s in scores if s is not None]
        return min(present) if present else 1.0


class InvoiceView(BaseModel):
    """An invoice as the scorer sees it. No ORM, no session."""

    id: int
    invoice_no: str
    issue_date: date
    due_date: date
    total_sen: int
    outstanding_sen: int


class CustomerView(BaseModel):
    """A customer as the scorer sees it."""

    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    phone_hmac: str | None = None
    language: str = "EN"


class SignalHit(BaseModel):
    """One row of the scorecard, kept so the explanation can cite it."""

    name: str
    awarded: int
    maximum: int
    matched: bool
    detail: str

    @property
    def missing(self) -> bool:
        return not self.matched


class Candidate(BaseModel):
    """One scored invoice."""

    invoice_id: int
    invoice_no: str
    outstanding_sen: int
    score: int
    signals: list[SignalHit] = Field(default_factory=list)

    @property
    def matched_signals(self) -> list[SignalHit]:
        return [s for s in self.signals if s.matched]

    @property
    def missing_signals(self) -> list[SignalHit]:
        return [s for s in self.signals if not s.matched]


class Allocation(BaseModel):
    """How much of a payment goes against which invoice."""

    invoice_id: int
    invoice_no: str
    amount_sen: int


class Decision(BaseModel):
    """The deterministic recommendation handed to a human."""

    classification: Literal[
        "EXACT_MATCH",
        "PARTIAL_PAYMENT",
        "OVERPAYMENT",
        "MULTI_INVOICE",
        "DUPLICATE",
        "UNMATCHED",
        "LOW_CONFIDENCE",
        "NOT_A_RECEIPT",
    ]
    confidence: int = 0
    candidates: list[Candidate] = Field(default_factory=list)
    allocations: list[Allocation] = Field(default_factory=list)
    explanation: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_exception(self) -> bool:
        return self.classification in EXCEPTION_CLASSIFICATIONS
