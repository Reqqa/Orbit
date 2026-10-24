"""Receipt reading. This is the ONLY place in Orbit where AI is used.

The model reads an image and returns the fields in docs/SPEC.md section 7.1. It
never decides a match, a classification or an approval - those are deterministic
rules in matching.py and classify.py.

Two implementations behind one interface:
  * MockExtractor   - looks the image up in seed/ground_truth.csv by SHA-256.
                      The default, so the demo never depends on a live API call.
  * ClaudeExtractor - Claude vision with a JSON schema the API enforces.

Results are cached in the `extractions` table by image SHA-256 (decision log 7).
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, get_settings
from app.models import Extraction
from app.schemas import ExtractedFields

log = logging.getLogger("orbit.extraction")

GROUND_TRUTH = BACKEND_DIR / "seed" / "ground_truth.csv"

# The model is given this and nothing else. Keeping it short and literal is what
# keeps the output stable.
PROMPT = """You are reading a payment receipt screenshot sent by a customer of a
Malaysian small business over WhatsApp.

Report only what you can actually see. Do not guess, do not infer an invoice, and do
not do any arithmetic. If a field is not visible, use null.

Set is_payment_receipt to false for anything that is not a proof of payment (a photo
of goods, a selfie, a delivery note, a plain chat screenshot).

field_confidence must give your own confidence from 0.0 to 1.0 for amount, date,
payer_name and reference_text. Be honest: use a low value when the text is cropped,
blurred or partly covered."""

# The API validates the response against this, so there is nothing to parse defensively.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_payment_receipt": {"type": "boolean"},
        "amount": {"type": ["number", "null"], "description": "ringgit, e.g. 850.00"},
        "currency": {"type": ["string", "null"]},
        "transaction_datetime": {"type": ["string", "null"], "description": "ISO 8601"},
        "payer_name": {"type": ["string", "null"]},
        "payee_name": {"type": ["string", "null"]},
        "channel": {"type": ["string", "null"], "description": "e.g. DuitNow Transfer"},
        "bank_or_wallet": {"type": ["string", "null"]},
        "reference_text": {"type": ["string", "null"]},
        "transaction_id": {"type": ["string", "null"]},
        "field_confidence": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "date": {"type": "number"},
                "payer_name": {"type": "number"},
                "reference_text": {"type": "number"},
            },
            "required": ["amount", "date", "payer_name", "reference_text"],
            "additionalProperties": False,
        },
        "notes": {"type": ["string", "null"]},
    },
    "required": ["is_payment_receipt", "amount", "field_confidence"],
    "additionalProperties": False,
}


class ExtractionFailed(RuntimeError):
    """Raised when the model could not be read even after one retry."""


def sha256_of(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


class Extractor(ABC):
    """Reads a receipt image into structured fields. Nothing more."""

    name: str = "abstract"

    @abstractmethod
    def extract(self, image_bytes: bytes) -> ExtractedFields: ...


class MockExtractor(Extractor):
    """Labelled answers from seed/ground_truth.csv, keyed by image SHA-256.

    Clearly a mock, on purpose: it is what makes the demo reproducible and it is
    what the accuracy script measures the real extractor against.
    """

    name = "mock"

    def __init__(self, ground_truth_path: Path | None = None) -> None:
        self._path = ground_truth_path or GROUND_TRUTH
        self._rows: dict[str, dict[str, str]] | None = None

    def _load(self) -> dict[str, dict[str, str]]:
        if self._rows is None:
            if not self._path.exists():
                raise ExtractionFailed(
                    f"{self._path} is missing. Generate it with: python -m seed.generate_receipts"
                )
            with self._path.open(newline="", encoding="utf-8") as handle:
                self._rows = {row["image_sha256"]: row for row in csv.DictReader(handle)}
        return self._rows

    def extract(self, image_bytes: bytes) -> ExtractedFields:
        digest = sha256_of(image_bytes)
        row = self._load().get(digest)
        if row is None:
            raise ExtractionFailed(
                f"image {digest[:12]} is not in ground_truth.csv; "
                "set LLM_PROVIDER=claude to read an unlabelled image"
            )
        return ExtractedFields.model_validate(_row_to_payload(row))


class ClaudeExtractor(Extractor):
    """Claude vision with an API-enforced JSON schema.

    Note on docs/SPEC.md section 7.1: it asks for temperature 0, but current Claude
    models reject sampling parameters outright. Determinism comes from the enforced
    response schema and a literal prompt instead (decision log 11).
    """

    name = "claude"

    def __init__(self, model: str = "claude-opus-5-5") -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise ExtractionFailed("ANTHROPIC_API_KEY is not set; use LLM_PROVIDER=mock")
        import anthropic  # imported lazily so the mock path needs no SDK

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = model

    def extract(self, image_bytes: bytes) -> ExtractedFields:
        import base64

        payload = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(image_bytes).decode(),
                },
            },
            {"type": "text", "text": PROMPT},
        ]

        last_error: Exception | None = None
        for attempt in (1, 2):  # one retry, then hand it to a human
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": payload}],
                    output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
                )
                text = next(b.text for b in response.content if b.type == "text")
                return ExtractedFields.model_validate(json.loads(text))
            except Exception as exc:  # noqa: BLE001 - any failure routes to a human
                last_error = exc
                log.warning("extraction attempt %s failed: %s", attempt, exc)

        raise ExtractionFailed(str(last_error))


def get_extractor() -> Extractor:
    """Pick the extractor named by LLM_PROVIDER. One seam."""
    provider = get_settings().llm_provider.strip().lower()
    if provider == "claude":
        return ClaudeExtractor()
    return MockExtractor()


def unreadable_receipt(reason: str) -> ExtractedFields:
    """The documented fallback: a receipt we could not read goes to a human.

    docs/SPEC.md section 7.1 - retry once on invalid JSON, then LOW_CONFIDENCE.
    """
    return ExtractedFields(
        is_payment_receipt=True,
        amount=None,
        field_confidence={"amount": 0.0, "date": 0.0, "payer_name": 0.0, "reference_text": 0.0},
        notes=f"Could not read this receipt automatically ({reason}). Please check it by hand.",
    )


def extract_for_message(
    session: Session,
    *,
    message_id: int,
    image_bytes: bytes,
) -> tuple[Extraction, ExtractedFields]:
    """Extract, caching by image SHA-256. Writes the row but does not commit."""
    digest = sha256_of(image_bytes)

    cached = session.execute(
        select(Extraction).where(Extraction.image_sha256 == digest).order_by(Extraction.id).limit(1)
    ).scalar_one_or_none()

    if cached is not None:
        log.info("extraction cache hit for %s", digest[:12])
        fields = ExtractedFields.model_validate(cached.raw_json)
        row = Extraction(
            message_id=message_id,
            raw_json=cached.raw_json,
            model_name=f"{cached.model_name} (cached)",
            image_sha256=digest,
        )
        session.add(row)
        session.flush()
        return row, fields

    extractor = get_extractor()
    try:
        fields = extractor.extract(image_bytes)
        model_name = extractor.name
    except ExtractionFailed as exc:
        fields = unreadable_receipt(str(exc))
        model_name = f"{extractor.name} (failed)"

    row = Extraction(
        message_id=message_id,
        raw_json=json.loads(fields.model_dump_json()),
        model_name=model_name,
        image_sha256=digest,
    )
    session.add(row)
    session.flush()
    return row, fields


def _row_to_payload(row: dict[str, str]) -> dict[str, Any]:
    """Turn one ground_truth.csv row into the section 7.1 payload shape."""

    def value(key: str) -> str | None:
        raw = (row.get(key) or "").strip()
        return raw or None

    confidence_raw = value("field_confidence_json")
    return {
        "is_payment_receipt": (row.get("is_payment_receipt") or "").strip().lower()
        in ("1", "true", "yes"),
        "amount": value("amount"),
        "currency": value("currency") or "MYR",
        "transaction_datetime": value("transaction_datetime"),
        "payer_name": value("payer_name"),
        "payee_name": value("payee_name"),
        "channel": value("channel"),
        "bank_or_wallet": value("bank_or_wallet"),
        "reference_text": value("reference_text"),
        "transaction_id": value("transaction_id"),
        "field_confidence": json.loads(confidence_raw) if confidence_raw else {},
        "notes": value("notes"),
    }
