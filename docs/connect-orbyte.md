# Connecting to Orbyte

Short answer to the question you are actually asking: **there is nothing to connect
to.** Not "we ran out of time" — as far as anything public shows, Orbyte has no
developer surface at all. The adapter in this repo is not a stub waiting for a key;
it is the correct answer to the brief. Read the next section, then the four
sentences you can say to a judge.

## 1. What we found when we looked (2026-10-24)

Searches run, and what came back:

- `Orbyte Alpha Red Solutions SME platform` — nothing. Closest unrelated hits:
  ORBYT, an Australian SME fintech (https://bouncewatch.com/company/orbyt), and
  Orbizer, a Polish SME tool. Neither is this.
- `"Orbyte Smart SME Challenge" hackathon 2026` — zero matches. Results were other
  2026 SME competitions (EU Youth Start-Up Challenge, Smart Industry Challenge).
- `Orbyte API developer documentation SME ERP` — no Orbyte docs. Only Oracle ERP
  material and an unrelated Barcelona studio, "Orbbyte"
  (https://www.linkedin.com/company/orbbyte).
- `"S.D.C. Hackathon" 2026 "Alpha Red Solutions"` — zero matches for either name.

Conclusion, stated plainly: **no public Orbyte API reference, no sandbox, no partner
or developer programme, and no public page for the hackathon itself.** That is a
negative result from public web search, not proof of absence — the organisers may
well run an internal platform with private docs. But there is no URL you could sign
up at today, and nothing for us to integrate against.

We reached no first-party Orbyte page at all, so every step in section 4 that touches
their side is marked **verify with the organisers**.

## 2. Why the repo is built the way it is

The brief explicitly allows defining our own API assumptions. So Orbit does, and
writes them down: `docs/SPEC.md` section 13 lists a seven-endpoint hub interface, and
`backend/app/connectors/orbyte.py` turns that list into an abstract `OrbyteConnector`
with one method per endpoint:

| Method | Assumed endpoint |
| --- | --- |
| `get_tenant` | `GET /orbyte/v1/tenants/{id}` |
| `list_users` | `GET /orbyte/v1/users?tenant={id}` |
| `list_customers` | `GET /orbyte/v1/customers?tenant={id}` |
| `list_open_invoices` | `GET /orbyte/v1/invoices?status=open` |
| `record_payment` | `POST /orbyte/v1/payments` (idempotency key) |
| `push_activity` | `POST /orbyte/v1/activity-log` |
| `send_notification` | `POST /orbyte/v1/notifications` |

`MockOrbyteConnector` implements all seven against the seeded synthetic data. Reads
are real reads, scoped by tenant; writes echo back; every dict carries
`"simulated": True`.

The seam is on the live path, not decoration:

- `backend/app/services/proposals.py:177` — every receipt is scored against invoices
  fetched through `connector.list_open_invoices(...)`, never a direct query.
- `backend/app/services/approval.py:162` — every approval calls `record_payment` and
  `push_activity`, then writes a `HUB_SYNCED` audit row recording whether the hub
  accepted them.

Take the connector away and the demo stops working. That is the point.

## 3. What to do about Orbyte before the deadline

Most likely: nothing technical. The job is to be able to explain the adapter in
twenty seconds. Two things.

1. Open `GET /api/orbyte/status` in the demo and be ready to show it. It names the
   live connector class, says why it is simulated, shows what it just read (tenant,
   users, customers, open invoices, outstanding), what it writes back, and the full
   assumed interface. That one response is your whole answer.
2. Learn these four sentences:

   > "Orbit is an Orbyte app module, not a standalone app. The hub owns the company,
   > users, customers and invoices; we only add the receivables workflow on top.
   > Live Orbyte access wasn't available, so — as the brief allows — we defined a
   > seven-endpoint interface, wrote it down in the spec, and shipped it as a
   > connector with a mock implementation over synthetic data. Every receipt is
   > matched against invoices fetched through that connector, and every approval
   > writes a payment and an activity event back through it, so pointing Orbit at a
   > real hub is one line in `get_connector` — nothing else changes."

Do not claim you integrated with Orbyte. The honest version is stronger, and a judge
who works there will know.

## 4. If the organisers hand over real access

**Verify with the organisers first:** base URL, auth scheme, their money unit, and
whether their invoice and payment field names match ours.

1. In `backend/app/connectors/orbyte.py`, add `class HttpOrbyteConnector(OrbyteConnector)`
   next to the mock. Same file, same ABC — the abstract methods are your checklist.
2. Implement all seven methods against their endpoints with `httpx`. Read base URL
   and token from env (add them to `.env.example`), never hardcoded.
3. Change the one line in `get_connector` (`orbyte.py:206`) to return the HTTP
   connector when those env vars are set and the mock otherwise. Touch no caller.
4. Map their field names onto exactly the keys the mock returns:
   - `get_tenant` -> `id, name, whatsapp_number, timezone, settings_json, found, simulated`
   - `list_users` -> `id, tenant_id, name, role, approval_limit_sen, simulated`
   - `list_customers` -> `id, tenant_id, name, aliases_json, language, assigned_sales_user_id, flags_json, simulated`
   - `list_open_invoices` -> `id, tenant_id, customer_id, invoice_no, issue_date, due_date, total_sen, outstanding_sen, status, simulated`
   - `record_payment` / `push_activity` / `send_notification` -> `accepted, simulated`,
     plus the echoed payload
5. Load-bearing keys — the ones the decision path actually reads, so get these right
   first: on invoices `id, invoice_no, issue_date, due_date, total_sen,
   outstanding_sen` (`invoice_view_from_hub`, proposals.py:230); on customers
   `id, name, aliases_json, language` (`customer_view_from_hub`, proposals.py:242);
   on writes `accepted` (approval.py reads it into the `HUB_SYNCED` audit row).
   Dates must be ISO strings — we `date.fromisoformat` them.
6. Money stays **integer sen** everywhere. If their API sends decimal ringgit,
   convert inside the connector and nowhere else.
7. Set `"simulated": False` on everything the HTTP connector returns, so
   `/api/orbyte/status` and the UI stop labelling it a simulation.
8. Keep the idempotency key as `orbit-proposal-{id}` (approval.py:174), so a retry
   cannot double-record a payment.
9. Run `..\.venv\Scripts\python.exe -m pytest` from `backend/`, then walk the journey
   by hand: Simulator -> upload receipt -> Approvals -> Approve, and check
   `/api/orbyte/status` names the new connector. The existing tests cover the mock
   only, not an HTTP connector, so that manual pass is the real check.

Nothing else in Orbit has to change. No model, service, route or frontend file talks
to the hub directly.

## 5. What Orbit deliberately does not send to the hub

Intentional, and worth saying out loud if asked:

- **The keyed phone HMAC.** How Orbit recognises a WhatsApp sender. It is our own
  index, derived with a local key, and it never crosses the boundary — so the hub
  cannot re-identify senders from anything we send.
- **Receipt images.** Customer-uploaded photos stay in Orbit's storage.
- **Extractions.** Raw model output is working data, often wrong before review; the
  hub should only ever see a reviewed result.
- **Match proposals.** Pre-approval state. Only the approved payment is a fact.
- **The hash-chained audit log.** Orbit's own tamper-evident record. We push a summary
  activity event to the hub's shared log, not the chain itself, so the chain stays
  verifiable in one place.

The rule behind all five: the hub gets decisions, not deliberation.
