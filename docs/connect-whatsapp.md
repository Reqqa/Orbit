# Connecting Orbit to a real WhatsApp number

Orbit runs its whole demo on the built-in simulator. Nothing below is needed for
the demo. This file is for the case where you want a real WhatsApp message to
land in Orbit.

**Status: unverified.** There is no Meta account in this repo, so no step here
has been run end to end from our side. Steps are marked "verify in the console"
where Meta's own docs do not state the detail and we would be guessing.

Checked against Meta's docs on 2026-10-24. Every URL cited is a live source, not
memory.

---

## What Orbit already has

| Thing | Where |
|---|---|
| Webhook, GET + POST | `/webhooks/whatsapp` in `backend/app/webhooks/whatsapp.py` |
| GET = Meta's handshake | compares `hub.verify_token` against `WHATSAPP_VERIFY_TOKEN`, echoes `hub.challenge`, else 403 |
| POST = inbound messages | verifies `X-Hub-Signature-256` against `WHATSAPP_APP_SECRET` **when that is set**, and skips verification when it is empty |
| Outbound sender | `backend/app/services/notify.py`, `CloudApiSender`, Graph `v26.0` |
| Media download | two-step Cloud API fetch in `_download_cloud_media`, runs only when `whatsapp_live` is true |

The four settings, already defined in `backend/app/config.py` and listed in
`.env.example`:

```
WHATSAPP_VERIFY_TOKEN=   # a string you invent; must match what you type in Meta
WHATSAPP_APP_SECRET=     # from Meta app -> App settings -> Basic
WHATSAPP_TOKEN=          # access token (temporary, then system-user)
WHATSAPP_PHONE_ID=       # the Cloud API phone number ID
```

`whatsapp_live` turns on the real send path only when **both** `WHATSAPP_TOKEN`
and `WHATSAPP_PHONE_ID` are set. Leave those two empty and Orbit stays on the
simulator no matter what else you fill in.

---

## 1. Accounts

1. **Create a Meta developer account.** You need a Facebook account (or a managed
   Meta account), then register as a developer.
   <https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started>

2. **Create an app with the WhatsApp use case.** In the App Dashboard, choose the
   use case **"Connect with customers through WhatsApp."** Meta's Get Started
   page names this exact use case; don't pick "Other" or a generic app type.
   <https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started>

3. **Pick or create a Business portfolio** during app creation. Meta's docs call
   this a Business portfolio (what older guides call Business Manager). Same URL
   as above.

4. **Connect a Messaging account** (a WhatsApp Business Account / WABA) in
   **WhatsApp -> API Setup**. Save its ID. Same URL as above.

## 2. Test number and temporary token

5. **Get the test business phone number.** Adding the WhatsApp product creates a
   test WhatsApp account, test Messaging account and test business phone number
   automatically. These have relaxed messaging limits and do not need a payment
   method on file to send templates.
   <https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform>

6. **Copy the phone number ID** from **WhatsApp -> API Setup**. This is
   `WHATSAPP_PHONE_ID`. Meta tells you explicitly to retain both the test phone
   number ID and the Messaging account ID.
   <https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started>

7. **Add your own mobile as a test recipient.** API Setup -> the **To** field ->
   **Manage phone number list**. The number gets a confirmation code. A test
   number can message **up to 5 recipient phone numbers**, and only numbers you
   have added and verified this way - it cannot reach real customers, and real
   customers cannot message it.
   <https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/>

8. **Generate the temporary access token.** API Setup -> **Generate access
   token**. Paste it into `WHATSAPP_TOKEN`.

   Lifetime: Meta's own page says only that it "expires quickly and is not
   suitable for development purposes" and does **not** state a number.
   Third-party integration docs say 23-24 hours and disagree with each other.
   Treat it as "good for one sitting" and **verify in the console** - the
   dashboard shows the expiry next to the token.
   <https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started>

## 3. Long-lived token (do this before you waste an afternoon)

9. In **Business Settings -> System users**, click **Add** and create a system
   user.

10. Select it, click **Assign Assets**, and assign:
    - your **app**, with **Manage app** under Full control
    - your **WhatsApp account**, with **Manage WhatsApp Business accounts** under Full control

11. Click **Generate token** and tick exactly these three permissions:
    - `business_management`
    - `whatsapp_business_messaging`
    - `whatsapp_business_management`

12. Copy the token immediately (it is shown once) into `WHATSAPP_TOKEN`.

Steps 9-12 are verbatim from Meta's Get Started page, including the permission
list.
<https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started>

Two notes. Assign the app to the system user **before** generating, or the token
can come out missing permissions. And vendor docs disagree on whether the default
expiry is 60 days or never - the generate dialog has the expiry selector, so
**verify in the console** and pick "Never" if it is offered.

## 4. A public HTTPS callback URL

Meta pushes webhooks to a URL on the public internet. `127.0.0.1:8000` is not
reachable from Meta, so for local testing you need a tunnel.

13. **Easiest tunnel, no account needed** - Cloudflare quick tunnel. Install
    `cloudflared`, then with Orbit running on port 8000:

    ```
    cloudflared tunnel --url http://localhost:8000
    ```

    It prints a `https://<random>.trycloudflare.com` URL, served over HTTPS, no
    account or domain required. It dies when you stop the process and you get a
    new random hostname next time, which means re-verifying the webhook in Meta
    each time. Cloudflare states there is no uptime guarantee for account-less
    tunnels.
    <https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/>

14. **Once Orbit is deployed to Replit**, use the Replit deployment URL instead.
    It is already public HTTPS and it is stable, so you verify the webhook once.
    Your callback URL is then `https://<your-replit-url>/webhooks/whatsapp`.

## 5. Configure the webhook in Meta

15. Decide a verify token. Any random string. Put the **same** string in
    `WHATSAPP_VERIFY_TOKEN` in your `.env` (or as a Replit Secret) and in the
    Meta dashboard. Restart Orbit so it picks up the value - `get_settings` is
    `lru_cache`d, so the process must restart.

16. Go to **App Dashboard -> WhatsApp -> Webhooks -> Configuration**. Set:
    - **Callback URL**: `https://<your-public-host>/webhooks/whatsapp`
    - **Verify token**: the string from step 15

    Click **Verify and save**.
    <https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/set-up-whatsapp-echo-bot>

17. What happens next, so you can read the logs: Meta sends a GET with
    `hub.mode`, `hub.verify_token` and `hub.challenge`. Orbit's `verify()`
    compares the token and replies 200 with the challenge as `text/plain`, or
    403 if it does not match. Meta re-sends this GET every time you edit the
    callback URL or the verify token.
    <https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint>

18. **Subscribe to the `messages` field.** After verification the dashboard shows
    the field list; subscribe to `messages`. That is the only field Orbit's
    `ingest_payload` reads - it looks for `changes[].field == "messages"` shaped
    payloads. (`message_template_status_update` is useful later if you submit
    templates and want to know when they are approved; Orbit ignores it.) Same
    echo-bot URL as step 16.

19. **Turn on signature checking.** Copy the App Secret from **App settings ->
    Basic** into `WHATSAPP_APP_SECRET`. Orbit then requires a valid
    `X-Hub-Signature-256` on every POST and returns 401 without one. Leave it
    empty while you are first getting a message through, then set it - that way a
    signature bug and a payload bug cannot confuse each other.

## 6. Point Orbit's database at the real numbers

Two rows have to change, or the message arrives and goes nowhere useful.

20. **Tenant 1's `whatsapp_number` must be the real test number.** Orbit resolves
    the tenant from `value.metadata.display_phone_number` in the payload. The
    seeded value is `+60127000001`.

    SQL:

    ```sql
    UPDATE tenants SET whatsapp_number = '15550123456' WHERE id = 1;
    ```

    Or one line, run from `backend/` with Orbit stopped:

    ```
    C:/Users/User/Documents/GitHub/Orbit/.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('orbit.db'); c.execute(\"update tenants set whatsapp_number='15550123456' where id=1\"); c.commit()"
    ```

    Use the number **exactly as Meta prints it in the payload**. Meta's test
    numbers are US `+1 555...` numbers, and `display_phone_number` is usually
    bare digits with no `+` and no spaces - but check one real payload in your
    log before trusting that. If it does not match, `_tenant_for` falls back to
    the lowest-id tenant, so a single-tenant demo still works; it just means a
    mismatch is silent.

21. **Point a seeded customer at your own mobile.** Customers are matched by a
    keyed HMAC of the sender's phone (`phone_hmac`), so a real phone matches
    nothing unless its number is in the database. Without this, the message is
    stored with `customer_id = NULL`, the proposal has no customer, and there is
    nothing to match an invoice against.

    Save this as `backend/link_my_phone.py`:

    ```python
    from app.db import SessionLocal
    from app.models import Customer
    from app.services.crypto import phone_hmac, encrypt_phone

    MY_PHONE = "+60123456789"   # your mobile, the one you verified in step 7

    with SessionLocal() as s:
        c = s.get(Customer, 1)
        c.phone_hmac = phone_hmac(MY_PHONE)
        c.phone_enc = encrypt_phone(MY_PHONE)
        s.commit()
        print("customer", c.id, c.name, "now points at", MY_PHONE)
    ```

    Run it from `backend/`:

    ```
    C:/Users/User/Documents/GitHub/Orbit/.venv/Scripts/python.exe link_my_phone.py
    ```

    `normalise_phone` strips punctuation and turns a leading `0` into `60`, so
    `+60 12-345 6789`, `012-3456789` and `60123456789` all land on the same
    hash. Customer 1 is `Azman Bin Sulaiman Mini Market` - note which invoices
    belong to it, because those are the ones your receipt can match.

    `PHONE_HMAC_KEY` must not change afterwards. Changing it invalidates every
    `phone_hmac` in the database, including this one.

## 7. Templates: which of the seven need Meta's approval

`backend/app/templates/messages.py` holds seven fixed templates. Meta's rule:
template messages generally require approval, and a template is **the only type
of message that can be sent to a WhatsApp user outside a customer service
window**. Replying inside the window can be free-form.
<https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform>

The window: replying to a customer's message opens a **24-hour customer service
window**, during which you can send non-template messages to that user.
<https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started>

**Need approval - business-initiated.** The three reminders in Orbit's chase
ladder, which go out with no customer message to answer:

- `REMINDER_HEADS_UP`
- `REMINDER_DUE`
- `REMINDER_FIRM`

Submit these three in **WhatsApp Manager -> Message templates**, in all three
languages (EN / BM / ZH), with the `{placeholders}` as numbered variables.
Category is **Utility**, not Marketing - they are payment reminders about an
existing transaction. Keep the wording exactly as it is in the file; promotional
wording gets reclassified to Marketing. Meta also requires user opt-in before
you send templates.
<https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform>

**Do not need approval - replies inside the 24-hour window.** These four are only
ever sent in response to a customer sending a receipt or an image:

- `PAYMENT_CONFIRMED`
- `PAYMENT_PARTIAL`
- `NOT_A_RECEIPT`
- `NEED_CLARIFICATION`

`CloudApiSender.send` posts `type: "text"` free-form. That is correct for those
four, and it will **not deliver the three reminders** once the window has closed.
Sending reminders for real needs a template-send branch Orbit does not have
today. That is a known gap, written down, not a bug.

## 8. Business verification - when you need it

A new Business portfolio starts at a **250** messaging limit. To get past it you
either verify your business directly, have your onboarding partner verify it, or
deliver 2,000 messages outside customer service windows to unique numbers within
30 days using high-quality templates. Meta then reviews message quality before
approving automatic scaling to 10,000 / 100,000 / unlimited.
<https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits>

For this project you do not need verification: the test number only messages the
5 recipients you verified by hand. You need verification when you register a
real business phone number and want to message an arbitrary customer. The exact
cap for an **unverified** account is where third-party sources disagree most
(250/day vs 50/day vs a 30-day trial), so **verify in the console** - WhatsApp
Manager shows the current limit on the number.

---

## Test it works

1. Start Orbit with all four settings filled in.
2. Check the handshake yourself before touching the dashboard:

   ```
   curl "https://<host>/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=<your-token>&hub.challenge=hello"
   ```

   Expect the body `hello`.
3. In the Meta dashboard, **Webhooks -> messages -> Test**. Orbit should log
   `MESSAGE_RECEIVED`. A test payload carries a fake phone, so expect
   `customer_known: false`.
4. From the mobile you verified in step 7, send a **text** to the test number.
   The Orbit message log should show it, linked to customer 1.
5. Send a **receipt image** from the same mobile. Orbit should log
   `MEDIA_DOWNLOADED`, then produce a proposal in Approvals.
6. Approve it. The confirmation reply goes out free-form, inside the 24-hour
   window your own message opened.

## Troubleshooting

**Webhook verification fails ("The callback URL or verify token couldn't be validated")**
- The verify token in `.env` and in the dashboard differ, or Orbit was not
  restarted after you changed `.env`.
- The tunnel is down, or you pasted the previous `trycloudflare.com` hostname.
- Run the curl in test step 2 first. A 403 means token mismatch; a connection
  error means a tunnel problem.

**Signature mismatch (401 "Payload signature did not match")**
- `WHATSAPP_APP_SECRET` is the **App Secret** from App settings -> Basic. It is
  not the access token and not the verify token.
- Anything that re-serialises the request body breaks the HMAC, because Orbit
  hashes the raw bytes. A proxy that rewrites JSON will do this; Cloudflare quick
  tunnels pass bytes through.
- To isolate: clear `WHATSAPP_APP_SECRET`, confirm the message arrives, then put
  it back.

**API returns 200 but the message is never delivered**
- Most likely the recipient is not one of the 5 verified test recipients. A test
  number goes nowhere else, quietly.
- Or the 24-hour window has closed and you sent free-form text. Meta accepts the
  call and does not deliver. This is the failure mode for the three reminders.
- With `messages` subscribed, the `statuses` array in the webhook carries
  `sent` / `delivered` / `failed` plus an error code. Orbit does not store
  statuses, so read it from the log.
- Check the number format: `to` should be digits with country code, no `+`, no
  spaces. `decrypt_phone` returns that form, e.g. `60123456789`.

**Media cannot be downloaded (`MEDIA_DOWNLOAD_FAILED` in the audit log)**
- The media URL from step 1 of the two-step download is short-lived (Meta
  documents roughly five minutes). If the background task was slow, or the
  process restarted between receiving and processing, it has expired. Resend the
  image.
- Step 2 needs the same `Authorization: Bearer` header even though the URL is
  signed. A 401 on the second GET usually means `WHATSAPP_TOKEN` expired - the
  classic symptom of the temporary token running out mid-session, which is why
  step 9 exists.
- An expired token breaks the whole send path too, not only media.
- The error text in the audit row is Meta's own message; it never contains the
  token.

---

## Honest status

None of this is verified from our side. There is no Meta account attached to this
repo, so `CloudApiSender`, `_download_cloud_media` and the webhook's signature
path have never run against `graph.facebook.com` - only against injected test
doubles. The steps above come from Meta's current documentation, cited inline,
not from having done it.

This is the project's hardest documented risk. It depends on an external account
approval we do not control, a token lifetime Meta does not publish a number for,
a tunnel with no uptime guarantee, and template approval for the three reminders
that has its own review queue. Any one of those can fail on the day.

The built-in simulator is the committed fallback and it needs none of this. It
posts the identical payload shape through `ingest_payload`, so the demo path and
the real path are the same code from the webhook inwards. Demo on the simulator.
Treat a live number as a stretch goal, and if it does not work, nothing is lost.
