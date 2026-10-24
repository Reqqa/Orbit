"""Inbound WhatsApp messages (docs/SPEC.md section 5.1 step 2).

Meta retries deliveries and expects a fast answer, so this returns 200 as soon as
the message is stored and does the reading and matching in a background task
(decision log 5). `wa_message_id` is unique, so a retry is a no-op.

The built-in simulator posts the same payload shape through `ingest_payload`, which
is what keeps the demo path and the real path identical.
"""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.media import load_media
from app.models import ACTOR_CUSTOMER, Customer, Tenant, WhatsappMessage
from app.services.audit import write_audit
from app.services.crypto import phone_hmac
from app.services.proposals import process_message

log = logging.getLogger("orbit.webhook")

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])


@router.get("/whatsapp", include_in_schema=True)
def verify(request: Request) -> Response:
    """Meta's verification handshake."""
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get(
        "hub.verify_token"
    ) == get_settings().whatsapp_verify_token:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token did not match.")


@router.post("/whatsapp")
async def receive(request: Request, background: BackgroundTasks) -> dict:
    """Store inbound messages, then process them out of band."""
    raw = await request.body()
    _check_signature(raw, request.headers.get("x-hub-signature-256"))
    payload = await request.json()

    with SessionLocal() as session:
        stored = ingest_payload(session, payload, simulated=False)
        session.commit()

    for message_id in stored:
        background.add_task(_process, message_id)

    return {"received": True, "stored": len(stored)}


def ingest_payload(
    session: Session,
    payload: dict[str, Any],
    *,
    simulated: bool = True,
    image_bytes_by_wa_id: dict[str, bytes] | None = None,
) -> list[int]:
    """Store every message in a Meta-shaped payload. Returns new message ids.

    Does not commit, so the caller controls the transaction.
    """
    new_ids: list[int] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            business_number = (value.get("metadata") or {}).get("display_phone_number")
            tenant = _tenant_for(session, business_number)
            if tenant is None:
                log.warning("no tenant for business number %r", business_number)
                continue

            for message in value.get("messages", []):
                wa_id = message.get("id")
                if not wa_id:
                    continue

                existing = session.execute(
                    select(WhatsappMessage.id).where(WhatsappMessage.wa_message_id == wa_id)
                ).scalar()
                if existing:
                    # Meta retried a delivery. Already handled.
                    log.info("duplicate wa_message_id %s ignored", wa_id)
                    continue

                sender = message.get("from", "")
                sender_hmac = phone_hmac(sender) if sender else None
                customer = _customer_for(session, tenant.id, sender_hmac)
                kind = message.get("type", "text")

                media_ref = None
                if kind == "image":
                    image = message.get("image") or {}
                    media_ref = image.get("orbit_media_ref") or image.get("id")

                row = WhatsappMessage(
                    tenant_id=tenant.id,
                    wa_message_id=wa_id,
                    direction="IN",
                    from_hmac=sender_hmac,
                    customer_id=customer.id if customer else None,
                    type=kind,
                    media_ref=media_ref,
                    text=(message.get("text") or {}).get("body"),
                    status="RECEIVED",
                    simulated=simulated,
                )
                session.add(row)
                session.flush()

                write_audit(
                    session,
                    tenant_id=tenant.id,
                    actor_type=ACTOR_CUSTOMER,
                    actor_id=customer.id if customer else None,
                    action="MESSAGE_RECEIVED",
                    entity_type="whatsapp_message",
                    entity_id=row.id,
                    after={
                        "type": kind,
                        "simulated": simulated,
                        "customer_known": customer is not None,
                    },
                )
                new_ids.append(row.id)

    return new_ids


def _process(message_id: int) -> None:
    """Background worker: read the receipt and build a proposal."""
    with SessionLocal() as session:
        message = session.get(WhatsappMessage, message_id)
        if message is None:
            return
        image_bytes = load_media(message.media_ref)
        if image_bytes is None and message.type == "image":
            log.warning(
                "message %s references media %r that is not stored locally; "
                "downloading Cloud API media needs WHATSAPP_TOKEN",
                message_id,
                message.media_ref,
            )
        try:
            process_message(session, message_id=message_id, image_bytes=image_bytes)
        except Exception:  # noqa: BLE001 - a background task must not take the app down
            session.rollback()
            log.exception("processing message %s failed", message_id)


def _check_signature(raw: bytes, header: str | None) -> None:
    """Verify Meta's payload signature when an app secret is configured."""
    secret = get_settings().whatsapp_app_secret
    if not secret:
        # No secret set means we are running on the simulator; nothing to verify.
        return
    if not header or not header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing payload signature.")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(header.removeprefix("sha256="), expected):
        raise HTTPException(status_code=401, detail="Payload signature did not match.")


def _tenant_for(session: Session, business_number: str | None) -> Tenant | None:
    if business_number:
        tenant = session.execute(
            select(Tenant).where(Tenant.whatsapp_number == business_number)
        ).scalar_one_or_none()
        if tenant is not None:
            return tenant
    # Single-tenant demo convenience: fall back to the first tenant.
    return session.execute(select(Tenant).order_by(Tenant.id).limit(1)).scalar_one_or_none()


def _customer_for(session: Session, tenant_id: int, sender_hmac: str | None) -> Customer | None:
    if not sender_hmac:
        return None
    return session.execute(
        select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.phone_hmac == sender_hmac
        )
    ).scalar_one_or_none()


def build_payload(
    *,
    business_number: str,
    from_number: str,
    wa_message_id: str,
    media_ref: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """A Meta-shaped payload, used by the simulator so both paths are identical."""
    message: dict[str, Any] = {"id": wa_message_id, "from": from_number, "timestamp": "0"}
    if media_ref:
        message["type"] = "image"
        message["image"] = {"orbit_media_ref": media_ref, "mime_type": "image/png"}
    else:
        message["type"] = "text"
        message["text"] = {"body": text or ""}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "orbit-simulated-waba",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_number,
                                "phone_number_id": "simulated",
                            },
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }
