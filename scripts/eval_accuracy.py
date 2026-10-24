"""Accuracy evaluation over the 50 labelled synthetic receipts.

docs/SPEC.md section 14 step 19, reporting the numbers section 11 asks for.

What it measures, in three parts:

  1. Extraction. Every PNG in backend/seed/receipts/ is read by the configured
     extractor (app.services.extraction.get_extractor) and each field is compared
     with the label in backend/seed/ground_truth.csv.
  2. Classification. The real decision path (app.services.proposals.decide) runs
     against a seeded tenant and the result is compared with
     expected_classification. Printed as a confusion matrix.
  3. Auto-match. The share of receipts whose top candidate scores at or above the
     strong-match threshold AND is the labelled invoice, with confident wrong
     answers counted separately.

Run it from either directory:

    cd backend && ../.venv/Scripts/python.exe ../scripts/eval_accuracy.py
    .venv/Scripts/python.exe scripts/eval_accuracy.py

Flags:

    --provider mock|claude   which extractor to use (default: the environment,
                             i.e. LLM_PROVIDER, which itself defaults to mock)
    --out PATH               where to write the markdown (default docs/accuracy.md)

The report is printed and the same markdown is written to docs/accuracy.md.

Nothing is written to the database. The decision path needs a session, so it gets
one, and that session is rolled back and closed at the end.

IMPORTANT, and printed in the report itself: with the mock extractor the
extraction numbers are 100% by construction, because the mock reads the label
file. They are a check that the plumbing is wired up, not a measurement of a
model. Only --provider claude measures a model.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_DIR / "backend"

# The backend package is rooted at backend/, and app.config resolves the database
# and the seed directory relative to it, so put it on the path and work from there.
sys.path.insert(0, str(BACKEND_DIR))

GROUND_TRUTH = BACKEND_DIR / "seed" / "ground_truth.csv"
RECEIPTS_DIR = BACKEND_DIR / "seed" / "receipts"

# Fields compared one by one, in the order they are reported.
FIELDS = (
    "amount",
    "transaction_datetime",
    "payer_name",
    "reference_text",
    "transaction_id",
    "is_payment_receipt",
)

MOCK_CAVEAT = (
    "With the mock extractor the extraction numbers are 100% BY CONSTRUCTION, "
    "because the mock reads the label file. This is not a measurement of the "
    "model. Run with --provider claude to measure the model."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Accuracy evaluation over the 50 labelled synthetic receipts."
    )
    parser.add_argument(
        "--provider",
        choices=("mock", "claude"),
        default=None,
        help="extractor to use; default is LLM_PROVIDER from the environment",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_DIR / "docs" / "accuracy.md"),
        help="where to write the markdown report",
    )
    return parser.parse_args()


# --- comparisons (docs/SPEC.md section 7.1 field types) ---


def norm_text(value) -> str | None:
    """Strings compare case-insensitively after stripping whitespace."""
    if value is None:
        return None
    text = " ".join(str(value).split()).strip().casefold()
    return text or None


def norm_minute(value) -> str | None:
    """Dates compare to the minute."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip())
        except ValueError:
            return value.strip() or None
    return value.replace(second=0, microsecond=0, tzinfo=None).isoformat(timespec="minutes")


def truth_cell(row: dict[str, str], key: str) -> str | None:
    raw = (row.get(key) or "").strip()
    return raw or None


def truth_values(row: dict[str, str]) -> dict[str, object]:
    """One ground_truth.csv row reduced to the comparable values."""
    from app.money import to_sen

    amount = truth_cell(row, "amount")
    return {
        "amount": to_sen(amount) if amount else None,
        "transaction_datetime": norm_minute(truth_cell(row, "transaction_datetime")),
        "payer_name": norm_text(truth_cell(row, "payer_name")),
        "reference_text": norm_text(truth_cell(row, "reference_text")),
        "transaction_id": norm_text(truth_cell(row, "transaction_id")),
        "is_payment_receipt": (row.get("is_payment_receipt") or "").strip().lower()
        in ("1", "true", "yes"),
    }


def extracted_values(fields) -> dict[str, object]:
    """The extractor's answer reduced to the same shape. Amount in integer sen."""
    return {
        "amount": fields.amount_sen,
        "transaction_datetime": norm_minute(fields.transaction_datetime),
        "payer_name": norm_text(fields.payer_name),
        "reference_text": norm_text(fields.reference_text),
        "transaction_id": norm_text(fields.transaction_id),
        "is_payment_receipt": bool(fields.is_payment_receipt),
    }


def pct(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100.0 * part / whole:.1f}%"


def main() -> int:
    args = parse_args()

    # The settings object is cached, so the provider has to be chosen before any
    # app module is imported.
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider

    # DATABASE_URL defaults to sqlite:///./orbit.db, which is relative to the
    # working directory. Without this, running from the repo root would create an
    # empty second database instead of reading backend/orbit.db. --out is resolved
    # before this, so it still points where the caller meant.
    out_path = Path(args.out).resolve()
    os.chdir(BACKEND_DIR)

    if not GROUND_TRUTH.exists():
        print(f"missing {GROUND_TRUTH}", file=sys.stderr)
        return 1
    if not RECEIPTS_DIR.exists():
        print(
            f"missing {RECEIPTS_DIR} - the images are gitignored, generate them with:\n"
            "  cd backend && python -m seed.generate_receipts",
            file=sys.stderr,
        )
        return 1

    from app.db import SessionLocal
    from app.models import Customer, Invoice
    from app.schemas import THRESHOLD_STRONG
    from app.services.extraction import ExtractionFailed, get_extractor
    from app.services.proposals import decide

    try:
        extractor = get_extractor()
    except ExtractionFailed as exc:
        print(f"cannot build the extractor: {exc}", file=sys.stderr)
        return 1

    with GROUND_TRUTH.open(newline="", encoding="utf-8") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda r: r["filename"])

    session = SessionLocal()
    lines: list[str] = []  # the markdown report

    try:
        field_right: Counter[str] = Counter()
        field_seen: Counter[str] = Counter()
        field_misses: list[tuple[str, str, object, object]] = []

        confusion: Counter[tuple[str, str]] = Counter()
        class_right = 0

        auto_right = 0  # top candidate >= threshold and it is the labelled invoice
        auto_wrong = 0  # top candidate >= threshold and it is a DIFFERENT invoice
        auto_wrong_detail: list[tuple[str, str, str, int]] = []
        no_strong = 0  # no candidate reached the threshold
        with_labelled = 0  # receipts that have a labelled invoice at all

        drift: list[str] = []
        read_failures: list[tuple[str, str]] = []

        for row in rows:
            filename = row["filename"]
            image_path = RECEIPTS_DIR / filename
            if not image_path.exists():
                read_failures.append((filename, "image file missing"))
                continue

            image_bytes = image_path.read_bytes()
            try:
                fields = extractor.extract(image_bytes)
            except ExtractionFailed as exc:
                read_failures.append((filename, str(exc)))
                continue

            # --- 1. per-field extraction accuracy ---
            truth = truth_values(row)
            got = extracted_values(fields)
            for name in FIELDS:
                field_seen[name] += 1
                if truth[name] == got[name]:
                    field_right[name] += 1
                else:
                    field_misses.append((filename, name, truth[name], got[name]))

            # --- 2. the real decision path ---
            tenant_id = int(row["tenant_id"])
            customer = (
                session.get(Customer, int(row["customer_id"])) if row["customer_id"] else None
            )
            decision = decide(session, tenant_id=tenant_id, customer=customer, fields=fields)

            expected = row["expected_classification"].strip()
            confusion[(expected, decision.classification)] += 1
            if expected == decision.classification:
                class_right += 1

            # --- 3. auto-match rate ---
            labelled = [n for n in (row["invoice_no"] or "").split("|") if n]
            with_labelled += 1 if labelled else 0
            top = decision.candidates[0] if decision.candidates else None
            if top is not None and top.score >= THRESHOLD_STRONG:
                if labelled and top.invoice_no in labelled:
                    auto_right += 1
                else:
                    auto_wrong += 1
                    auto_wrong_detail.append(
                        (filename, "|".join(labelled) or "(none)", top.invoice_no, top.score)
                    )
            else:
                no_strong += 1

            # Did an earlier demo run already settle the labelled invoice? That
            # changes the decision path, so say so rather than let it read as an
            # extraction or matching error.
            for invoice_no in labelled:
                invoice = (
                    session.query(Invoice)
                    .filter(Invoice.tenant_id == tenant_id, Invoice.invoice_no == invoice_no)
                    .one_or_none()
                )
                if invoice is not None and invoice.outstanding_sen == 0:
                    drift.append(
                        f"{filename}: {invoice_no} has nothing outstanding in this database"
                    )

        total = len(rows) - len(read_failures)

        # ------------------------------------------------------------------
        # report
        # ------------------------------------------------------------------
        out = lines.append
        out("# Orbit accuracy on the 50 synthetic receipts")
        out("")
        out(
            f"Extractor: **{extractor.name}** "
            f"(LLM_PROVIDER={os.environ.get('LLM_PROVIDER', 'mock')})"
        )
        out(f"Receipts evaluated: **{total}** of {len(rows)} labelled rows")
        out(
            "Generated by `scripts/eval_accuracy.py` on "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}."
        )
        out("")
        if extractor.name == "mock":
            out(f"> {MOCK_CAVEAT}")
            out("")
        out("Synthetic data throughout: the receipts are generated images, not real ones.")
        out("")

        out("## Extraction, per field")
        out("")
        out("| Field | Correct | Of | Accuracy |")
        out("|---|---:|---:|---:|")
        for name in FIELDS:
            out(
                f"| {name} | {field_right[name]} | {field_seen[name]} "
                f"| {pct(field_right[name], field_seen[name])} |"
            )
        all_right = sum(field_right[n] for n in FIELDS)
        all_seen = sum(field_seen[n] for n in FIELDS)
        out(
            f"| **all fields** | **{all_right}** | **{all_seen}** "
            f"| **{pct(all_right, all_seen)}** |"
        )
        out("")
        out("Amount is compared in integer sen, dates to the minute, strings")
        out("case-insensitively after stripping whitespace. A field the label leaves")
        out("blank counts as correct only when the extractor also left it blank.")
        out("")

        if field_misses:
            out("Field mismatches:")
            out("")
            out("| Receipt | Field | Labelled | Extracted |")
            out("|---|---|---|---|")
            for filename, name, want, gotv in field_misses:
                out(f"| {filename} | {name} | `{want}` | `{gotv}` |")
            out("")

        out("## Classification, against the real decision path")
        out("")
        out(
            f"Overall classification accuracy: **{class_right}/{total} "
            f"({pct(class_right, total)})**"
        )
        out("")
        labels = sorted({e for e, _ in confusion} | {g for _, g in confusion})
        short = {label: label.replace("_", " ").title() for label in labels}
        out("Confusion matrix, expected down the side, got across the top:")
        out("")
        out("| expected \\ got | " + " | ".join(short[c] for c in labels) + " | total |")
        out("|---" * (len(labels) + 2) + "|")
        for expected in labels:
            row_total = sum(v for (e, _), v in confusion.items() if e == expected)
            if row_total == 0:
                continue
            cells = []
            for gotc in labels:
                count = confusion[(expected, gotc)]
                if count and expected == gotc:
                    cells.append(f"**{count}**")
                else:
                    cells.append(str(count) if count else ".")
            out(f"| {short[expected]} | " + " | ".join(cells) + f" | {row_total} |")
        out("")

        out("## Auto-match rate")
        out("")
        out(f"Threshold: a top candidate scoring {THRESHOLD_STRONG} or more out of 100.")
        out("")
        out("| Outcome | Count | Share |")
        out("|---|---:|---:|")
        out(
            f"| Top candidate >= {THRESHOLD_STRONG} and it is the labelled invoice "
            f"| {auto_right} | {pct(auto_right, total)} |"
        )
        out(
            f"| Top candidate >= {THRESHOLD_STRONG} and it is the WRONG invoice "
            f"| {auto_wrong} | {pct(auto_wrong, total)} |"
        )
        out(
            f"| No candidate reached {THRESHOLD_STRONG} (routed to a human) "
            f"| {no_strong} | {pct(no_strong, total)} |"
        )
        out("")
        out(
            f"Auto-match rate: **{auto_right}/{total} ({pct(auto_right, total)})** of all "
            f"receipts, or **{auto_right}/{with_labelled} ({pct(auto_right, with_labelled)})** "
            "of the receipts that have a labelled invoice at all. The second denominator "
            f"excludes the {total - with_labelled} receipts that are not a payment against a "
            "known invoice (the not-a-receipt images and the unknown-payer transfers), which "
            "can never auto-match by definition."
        )
        out("")
        out(
            "The score and the classification are separate: a receipt can score 100 on the "
            "right invoice and still be held for a human, because a low per-field confidence "
            "sends it to LOW_CONFIDENCE whatever the score. That is the intended direction "
            "to fail in."
        )
        out("")
        if auto_wrong:
            out("**Confident wrong answers.** In a payments product this is the expensive")
            out("failure mode: a high score on the wrong invoice is what an approver is")
            out("most likely to wave through. Every one of them is listed here.")
            out("")
            out("| Receipt | Labelled invoice | Top candidate | Score |")
            out("|---|---|---|---:|")
            for filename, want, gotv, score in auto_wrong_detail:
                out(f"| {filename} | {want} | {gotv} | {score} |")
        else:
            out(
                "**No confident wrong answers:** no receipt scored "
                f"{THRESHOLD_STRONG} or more on an invoice other than the labelled one."
            )
            out("A confident wrong answer is the expensive failure mode in a payments")
            out("product, so it is counted separately whether or not any occur.")
        out("")
        out("No payment is recorded without a human approval, whatever the score")
        out("(CLAUDE.md non-negotiable 5).")
        out("")

        out("## Caveats")
        out("")
        if extractor.name == "mock":
            out(f"- {MOCK_CAVEAT}")
        out("- The receipts, customers and invoices are synthetic and generated from a")
        out("  deterministic seed. These numbers describe that test set only.")
        out("- Each receipt is evaluated on its own against the ledger as it stands.")
        out("  Duplicate detection needs the earlier copy of the payment to be recorded")
        out("  already, and this evaluation approves nothing, so a receipt labelled")
        out("  DUPLICATE is only classified DUPLICATE here when that earlier payment is")
        out("  already in the database. The DUPLICATE row of the confusion matrix")
        out("  therefore understates what the running system does.")
        if drift:
            out("- This database is no longer in its freshly seeded state, which changes")
            out("  the decision path for the receipts below. Re-seed with")
            out("  `python -m seed.generate_data` for comparable numbers:")
            for note in sorted(set(drift)):
                out(f"  - {note}")
        if read_failures:
            out("- Receipts that could not be read at all:")
            for filename, reason in read_failures:
                out(f"  - {filename}: {reason}")
        out("")

        report = "\n".join(lines) + "\n"
        print(report)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"written to {out_path}")
        return 0
    finally:
        # Read-only by intent: nothing here commits, and the session is rolled back.
        session.rollback()
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
