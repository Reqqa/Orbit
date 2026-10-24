"""Outbound WhatsApp messages (docs/SPEC.md sections 5.1 step 8 and 7.4).

Wording always comes from app.templates.messages; this module only decides how a
body gets out of the building. Two senders behind one interface: the simulator
used for the demo, and the real Meta Cloud API path which cannot be exercised
without a Meta account.

Nothing here commits. The caller owns the transaction so that the message row and
the audit row land with the change that caused them (CLAUDE.md rule 3).
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ACTOR_SYSTEM, Customer, WhatsappMessage
from app.services import crypto
from app.services.audit import write_audit
from app.templates import messages

# The one place the Graph API version is written down. app.webhooks.whatsapp
# imports this constant so the send path and the media-download path can never
# drift apart.
#
# v20.0, which this file used to hardcode, expired on 2026-09-24; calls to an
# expired version are silently served by the next usable one, which is exactly
# the kind of surprise you do not want mid-demo. v26.0 is the newest version at
# the time of writing (released 2026-07-29).
# https://developers.facebook.com/docs/graph-api/changelog/versions
# https://developers.facebook.com/blog/post/2026/07/29/introducing-graph-api-v26-and-marketing-api-v26/
GRAPH_API_VERSION = "v26.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Both Cloud API calls are single small HTTP round trips to Meta. Long enough to
# survive a slow hop, short enough that a hung connection cannot wedge a
# background task.
HTTP_TIMEOUT_SECONDS = 20.0


class Sender(ABC):
    """Anything that can put a message body in front of a customer."""

    @abstractmethod
    def send(self, *, tenant_id: int, to_phone: str, body: str) -> dict[str, Any]:
        """Send one text message. Returns at least {"sent": bool, "wa_message_id": str}."""


class SimulatorSender(Sender):
    """Records the message as an OUT row instead of calling WhatsApp.

    This is what the demo runs on: every message is marked simulated=True so the
    dashboard can label it honestly (CLAUDE.md rule 6).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def send(self, *, tenant_id: int, to_phone: str, body: str) -> dict[str, Any]:
        """Store an OUT row and report it as sent. `to_phone` is never stored."""
        wa_message_id = f"sim-out-{uuid.uuid4().hex}"
        self.session.add(
            WhatsappMessage(
                tenant_id=tenant_id,
                wa_message_id=wa_message_id,
                direction="OUT",
                type="text",
                text=body,
                status="SENT",
                simulated=True,
            )
        )
        self.session.flush()
        return {"sent": True, "simulated": True, "wa_message_id": wa_message_id}


class CloudApiSender(Sender):
    """The real Meta WhatsApp Cloud API path.

    UNVERIFIED: there is no Meta account in this repo, so no line of this class
    has ever been run against graph.facebook.com. The request shape follows
    https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
    and the seam is exercised in both directions by injecting `http_post`.

    A real deployment needs WHATSAPP_TOKEN (a permanent system-user access
    token) and WHATSAPP_PHONE_ID (the Cloud API phone number id). Business-
    initiated messages outside a 24-hour customer service window must also be
    registered as approved templates with Meta; the free-text send below only
    reaches a customer who messaged first, which is the whole of Orbit's flow.

    `http_post(url, headers, json_body) -> dict` stays injectable so tests can
    capture the request without a network. When it is not supplied, httpx is
    used directly.
    """

    def __init__(
        self,
        http_post: Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]] | None = None,
        *,
        session: Session | None = None,
    ) -> None:
        settings = get_settings()
        self.token = settings.whatsapp_token
        self.phone_id = settings.whatsapp_phone_id
        self.http_post = http_post or _httpx_post
        # Optional: when a session is given, a live send also lands an OUT row
        # with simulated=False, so the dashboard message log and
        # notify_customer's customer_id backfill work the same as the simulator.
        self.session = session

    def send(self, *, tenant_id: int, to_phone: str, body: str) -> dict[str, Any]:
        """POST one text message to the Cloud API. UNVERIFIED against Meta."""
        if not (self.token and self.phone_id):
            raise NotImplementedError("configure WHATSAPP_TOKEN and WHATSAPP_PHONE_ID")

        response = self.http_post(
            f"{GRAPH_BASE_URL}/{self.phone_id}/messages",
            # Never logged: the Authorization header is built here and nowhere
            # else, and no error path in this module echoes headers.
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": body}},
        )
        wa_message_id = (response.get("messages") or [{}])[0].get("id", "")

        if self.session is not None and wa_message_id:
            self.session.add(
                WhatsappMessage(
                    tenant_id=tenant_id,
                    wa_message_id=wa_message_id,
                    direction="OUT",
                    type="text",
                    text=body,
                    status="SENT",
                    simulated=False,
                )
            )
            self.session.flush()

        return {"sent": bool(wa_message_id), "simulated": False, "wa_message_id": wa_message_id}


def _httpx_post(
    url: str, headers: dict[str, str], json_body: dict[str, Any]
) -> dict[str, Any]:
    """Default HTTP transport for CloudApiSender. UNVERIFIED against Meta.

    httpx is imported lazily so that the simulator path, which is the demo,
    never needs it at import time.
    """
    import httpx

    response = httpx.post(url, headers=headers, json=json_body, timeout=HTTP_TIMEOUT_SECONDS)
    if response.status_code // 100 != 2:
        raise RuntimeError(
            f"WhatsApp Cloud API returned {response.status_code}: {graph_error_message(response.text)}"
        )
    return response.json()


def graph_error_message(response_text: str) -> str:
    """Meta's own error text from a Graph API error body, for a useful exception.

    Graph errors look like {"error": {"message": ..., "code": ..., ...}}. The
    body never contains the access token, which is sent as a header, so this is
    safe to put in an exception message or a log line.
    """
    try:
        import json

        error = (json.loads(response_text) or {}).get("error") or {}
    except ValueError:
        return response_text[:500]
    if not error:
        return response_text[:500]
    parts = [str(error.get("message", "")).strip()]
    for key in ("code", "error_subcode", "error_data", "fbtrace_id"):
        if error.get(key) not in (None, "", {}):
            parts.append(f"{key}={error[key]}")
    return " ".join(part for part in parts if part)[:500]


def get_sender(session: Session) -> Sender:
    """The sender Orbit uses: the real Cloud API when one is configured.

    UNVERIFIED: the CloudApiSender branch has never run against a real Meta
    account. With no WhatsApp settings set - which is the demo - this returns
    exactly the SimulatorSender it always did.
    """
    if get_settings().whatsapp_live:
        return CloudApiSender(session=session)
    return SimulatorSender(session)


def notify_customer(
    session: Session,
    *,
    tenant_id: int,
    customer: Customer,
    template_id: str,
    **values: object,
) -> dict[str, Any]:
    """Render a pre-approved template in the customer's language, send it, audit it.

    Does not commit. The returned dict and the audit row carry a masked phone only.
    """
    body = messages.render(template_id, customer.language, **values)
    to_phone = crypto.decrypt_phone(customer.phone_enc)
    masked = crypto.mask_phone(to_phone)

    result = get_sender(session).send(tenant_id=tenant_id, to_phone=to_phone, body=body)

    # The OUT row is created by the sender, which does not know the customer.
    out_row = session.execute(
        select(WhatsappMessage)
        .where(WhatsappMessage.tenant_id == tenant_id)
        .where(WhatsappMessage.wa_message_id == result["wa_message_id"])
    ).scalar_one_or_none()
    if out_row is not None:
        out_row.customer_id = customer.id
        session.flush()

    write_audit(
        session,
        tenant_id=tenant_id,
        actor_type=ACTOR_SYSTEM,
        action="CUSTOMER_NOTIFIED",
        entity_type="customer",
        entity_id=customer.id,
        after={
            "template_id": template_id,
            "language": customer.language,
            "to_phone_masked": masked,
            "wa_message_id": result.get("wa_message_id"),
            "simulated": result.get("simulated", True),
            "body": body,
        },
    )
    return {**result, "body": body, "to_phone_masked": masked, "template_id": template_id}
