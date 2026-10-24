"""Money handling. Every amount in Orbit is an integer number of sen.

RM 850.00 is 85000. There are no floats in this module and there must be none
anywhere else in the codebase (see CLAUDE.md).
"""

from decimal import Decimal, InvalidOperation

SEN_PER_RINGGIT = 100


class MoneyError(ValueError):
    """Raised when a value cannot be read as an amount of money."""


def to_sen(value: str | int | Decimal) -> int:
    """Convert a ringgit amount to integer sen.

    Accepts "850", "850.00", "RM 850.00", "1,250.50", Decimal or int ringgit.
    Rejects anything negative or unparseable.
    """
    if isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, Decimal):
        amount = value
    else:
        cleaned = str(value).strip().upper()
        for junk in ("RM", "MYR", ",", " "):
            cleaned = cleaned.replace(junk, "")
        if not cleaned:
            raise MoneyError("empty amount")
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise MoneyError(f"cannot read amount: {value!r}") from exc

    if amount < 0:
        raise MoneyError(f"amount must not be negative: {value!r}")

    sen = (amount * SEN_PER_RINGGIT).to_integral_value()
    return int(sen)


def fmt_sen(sen: int) -> str:
    """Format integer sen for display: 85000 -> 'RM 850.00'."""
    ringgit, remainder = divmod(int(sen), SEN_PER_RINGGIT)
    return f"RM {ringgit:,}.{remainder:02d}"
