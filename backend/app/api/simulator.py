"""The WhatsApp simulator and the reusable receipt-analysis endpoint.

The simulator is the fallback for our hardest risk: WhatsApp Business API access
(docs/SPEC.md section 12). It builds a genuine Meta-shaped payload and pushes it
through the same ingestion code as the real webhook, so the pipeline under test is
the pipeline that ships. Everything it produces is labelled simulated.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.session import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.media import save_media
from app.models import Customer, Tenant, WhatsappMessage
from app.money import fmt_sen
from app.schemas import Candidate
from app.services.crypto import decrypt_phone
from app.services.extraction import get_extractor, sha256_of
from app.services.proposals import decide, process_message
from app.webhooks.whatsapp import build_payload, ingest_payload

router = APIRouter(tags=["simulator"])


def _require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404, detail="The simulator is only available in demo mode.")


@router.post("/api/simulator/send")
async def simulator_send(
    customer_id: int = Form(...),
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict:
    """Pretend a customer sent a receipt, and run the real pipeline on it."""
    _require_demo_mode()

    customer = session.get(Customer, customer_id)
    if customer is None or customer.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="No such customer.")
    tenant = session.get(Tenant, principal.tenant_id)

    image_bytes = await file.read() if file is not None else None
    if image_bytes is None and not text:
        raise HTTPException(status_code=400, detail="Attach a receipt image or type a message.")

    media_ref = save_media(image_bytes) if image_bytes else None
    payload = build_payload(
        business_number=tenant.whatsapp_number,
        from_number=decrypt_phone(customer.phone_enc),
        wa_message_id=f"sim-{uuid.uuid4().hex}",
        media_ref=media_ref,
        text=text,
    )

    message_ids = ingest_payload(session, payload, simulated=True)
    session.commit()
    if not message_ids:
        raise HTTPException(status_code=409, detail="That message was already received.")

    message_id = message_ids[0]
    # Run it inline rather than in the background: the demo should show the result
    # immediately, and it is the same function the webhook's background task calls.
    proposal = process_message(session, message_id=message_id, image_bytes=image_bytes)

    return {
        "simulated": True,
        "message_id": message_id,
        "proposal_id": proposal.id if proposal else None,
        "classification": proposal.classification if proposal else None,
        "confidence": proposal.confidence if proposal else None,
        "requested_approver_role": proposal.requested_approver_role if proposal else None,
    }


@router.get("/api/simulator/thread/{customer_id}")
def simulator_thread(
    customer_id: int,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> list[dict]:
    """The chat as the customer would see it, both directions."""
    _require_demo_mode()
    customer = session.get(Customer, customer_id)
    if customer is None or customer.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="No such customer.")

    rows = session.execute(
        select(WhatsappMessage)
        .where(
            WhatsappMessage.tenant_id == principal.tenant_id,
            WhatsappMessage.customer_id == customer.id,
        )
        .order_by(WhatsappMessage.id)
    ).scalars()

    return [
        {
            "id": row.id,
            "direction": row.direction,
            "type": row.type,
            "text": row.text,
            "media_url": f"/api/media/{row.media_ref}" if row.media_ref else None,
            "received_at": row.received_at.isoformat(),
            "simulated": row.simulated,
        }
        for row in rows
    ]


@router.post("/v1/receipts/analyze")
async def analyze_receipt(
    file: UploadFile = File(...),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict:
    """Reusable building block: image in, fields and match candidates out.

    Read-only. Nothing is recorded, nothing is approved. This is the surface another
    Orbyte module would call (docs/SPEC.md section 13).
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Send an image.")

    extractor = get_extractor()
    try:
        fields = extractor.extract(image_bytes)
    except Exception as exc:  # noqa: BLE001 - report it, do not record anything
        raise HTTPException(status_code=422, detail=f"Could not read that image: {exc}") from exc

    decision = decide(session, tenant_id=principal.tenant_id, customer=None, fields=fields)

    return {
        "image_sha256": sha256_of(image_bytes),
        "model_name": extractor.name,
        "extracted": fields.model_dump(mode="json"),
        "amount_display": fmt_sen(fields.amount_sen) if fields.amount_sen else None,
        "classification": decision.classification,
        "confidence": decision.confidence,
        "candidates": [_candidate(c) for c in decision.candidates[:5]],
        "explanation": decision.explanation,
        "recorded": False,
        "note": "Analysis only. Orbit records nothing without a human approval.",
    }


def _candidate(candidate: Candidate) -> dict:
    return {
        "invoice_id": candidate.invoice_id,
        "invoice_no": candidate.invoice_no,
        "outstanding_display": fmt_sen(candidate.outstanding_sen),
        "score": candidate.score,
        "signals": [s.model_dump() for s in candidate.signals],
    }
