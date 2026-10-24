# Orbit demo script

Shot-by-shot script for the YouTube Unlisted submission video.
Runs to 5:00 at full length, and the closing beat can end short if you are tight. This
refines the timing table in
[SPEC.md](SPEC.md) section 15: the segments and their order are the same, but the
boundaries moved to give the Orbyte segment the time it needs now that it shows a live API
response. Where the two disagree, this file is the one to shoot from.

Everything below is shootable against the software as it stands today. No mockups,
no slides pretending to be screens. Where something is simulated, the presenter says so
in the same sentence.

**Screens used:** Today `/today`, Approvals `/approvals`, Ledger `/ledger`,
Chasing `/chasing`, Customers `/customers`, Audit log `/audit`, WhatsApp simulator
`/simulator`, Settings `/settings`, plus the OpenAPI page at `/docs`.

**URLs.** In development the dashboard is at `http://localhost:3000` and the Python API
at `http://localhost:8000`, so the OpenAPI page is `http://localhost:8000/docs`. In a
built deployment FastAPI serves the exported dashboard from `frontend/out`, so
everything — screens and `/docs` — is on one URL. **Shoot on the built deployment.** The
rest of the script works either way, but the Orbyte segment calls `/api/orbyte/status`
from `/docs` and that only reflects the role switcher when the dashboard and the API share
an origin, because the session is a signed cookie. On `localhost:8000/docs` with no cookie,
demo mode falls back to the first Owner in the database, so the tenant switch would not
show. The one-URL point is also worth saying out loud.

---

## Timing table

| Time | Segment | Rubric criterion earned |
|---|---|---|
| 0:00–0:25 | The owner's evening (problem) | Innovation & Creativity: specific real pain point |
| 0:25–0:50 | One sentence and the five steps | Clarity of Proposal |
| 0:50–2:35 | Live core journey, simulator to paid invoice | Feasibility of Build; Problem-Solution Fit |
| 2:35–3:15 | Edge cases: duplicate, partial, low confidence | Problem-Solution Fit: accuracy and consistency |
| 3:15–3:45 | Role switch refused, and the audit chain breaking | Problem-Solution Fit: people stay in control |
| 3:45–4:05 | Chasing batch | Innovation & Creativity: second burden removed |
| 4:05–4:42 | Orbyte connector live on screen, tenant switch, numbers | Orbyte fit; business benefit; clarity |
| 4:42–5:00 | Hardest risk and fallback | Feasibility of Build |

The Orbyte segment is now the second longest after the core journey, because it shows a
live API response rather than describing an adapter. The twelve extra seconds come from
the outcome beat (25 to 20), chasing (25 to 20) and the closing risk beat (20 to 18).
Everything else keeps its old budget, and the hard maximum is still 5:00.

---

## 0:00–0:25 — The owner's evening

**On screen.** No Orbit yet. A phone screen recording of the WhatsApp simulator's
customer side, scrolled so three receipt images sit in the thread, next to a spreadsheet
window with an invoice list and an empty "paid?" column. A small caption burned in at the
bottom: *Synthetic data. Simulated WhatsApp channel.* Cursor moves between the two
windows, zooming into a receipt, then hunting the invoice row.

**Presenter says.**

> It is nine at night. Lim Wei Keong runs a hardware supplier. Today four customers paid
> him, and all four sent a screenshot on WhatsApp. He opens each one, reads the amount,
> finds the invoice in his spreadsheet, types it in, replies thank you, and makes a note
> to chase the ones who have not paid. Two to four minutes each, every evening, and if he
> keys in the wrong invoice nobody notices for a month. This is synthetic data standing in
> for a real evening, but the evening is real: this is how a lot of Malaysian micro
> businesses actually get paid.

---

## 0:25–0:50 — One sentence and the five steps

**On screen.** The Today screen at `/today`, full window. The three cards are visible:
Needs your approval, Overdue, Received this week. Then the architecture diagram from
[SPEC.md](SPEC.md) section 6.1 as a still, held for about eight seconds, with the five steps
highlighted left to right.

**Presenter says.**

> Orbit is payment reconciliation for the Orbyte hub. Five steps. A receipt arrives on
> WhatsApp. One AI call reads the image — that is the only place a model is used. A
> deterministic hundred-point scorecard matches it to an invoice. A human approves. The
> ledger updates, the customer gets a templated confirmation, and the whole thing lands in
> an append-only audit log. Matching, scoring, approval limits and chase scheduling are
> plain rules, not model opinions.

---

## 0:50–2:35 — Live core journey

This is the segment that must work. One take, no cuts.

### 0:50–1:15 — Send the receipt

**On screen.** `/simulator`. Point at the amber note at the top — *Simulated channel.
Identical webhook payloads to the real WhatsApp Cloud API, so the pipeline being
demonstrated is the one that ships.* In **Sending as**, choose
`Khoo Boon Hwa Mini Market · RM 847.00 outstanding`. In **Receipt photo**, choose
`backend/seed/receipts/003-exact-match.png`. In **Message**, type `Paid already boss`.
Press **Send**. The receipt image appears in the customer's thread.

**Presenter says.**

> This is Orbit's own WhatsApp simulator, and it is labelled as simulated right there.
> The real Cloud API path is written — set a token and a phone id and the sender switches
> to Meta — but we have no Meta business account, so that path has never run against
> Meta and the whole demo runs on the simulator by design. The simulator posts the same
> webhook payload shape the real Cloud API posts, so everything behind this screen is the
> code that would run in production. I am the customer. Here is my receipt, and a message as careless as a real
> one: paid already boss.

### 1:15–1:45 — Extraction and the match

**On screen.** The right-hand panel, the owner's phone, fills in. Badges: **Exact Match**,
**Confidence 95%**, **FINANCE must approve**. Below it the sentence *Orbit has written a
proposal and recorded nothing. A human decides what happens next.* Press
**Open the approval inbox**.

**Presenter says.**

> One model call read the image. In this demo the extractor is in mock mode: it looks up
> the labelled answer for this image by its SHA-256, so the demo never needs a live API
> call. Switch one environment variable and the same code path calls Claude vision with an
> API-enforced JSON schema. Either way the model only reads. The scorecard gave it
> ninety-five out of a hundred — it lost the last five points because this customer has
> more than one invoice open, so the case is not completely unambiguous — and it has
> recorded nothing at all. It wrote a proposal and asked for a human. Because this is a
> clean exact match under two thousand ringgit, it went to Finance rather than the owner.

### 1:45–2:15 — Approve

**On screen.** `/approvals`. One card: receipt image on the left, extracted fields on the
right — amount RM 847.00, payer, reference `INV-1009`, transaction id. Headline *Matches
INV-1009, RM 847.00*, label **Strong match**. Expand **Why we think so** and let the lines
sit on screen long enough to read. Hover **Edit** without clicking, to show it exists.
Press **Approve**.

**Presenter says.**

> Receipt on the left, what we read on the right, and a plain-language reason: the amount
> equals the outstanding balance, the reference contains the invoice number, the payer name
> matches the customer, the sender's phone is on file. No jargon, no probability talk. If
> any of it were wrong, Edit lets the approver correct the fields and we store both the
> original extraction and the corrected values, so we can measure how often humans have to
> fix us. This one is right. Approve.

### 2:15–2:35 — The outcome

**On screen.** Back to `/simulator` for three seconds: the outbound message in the thread,
*Thanks Khoo Boon Hwa Mini Market, RM 847.00 received for INV-1009. Fully settled — thank
you!* Then `/ledger`, filter **Paid**, click `INV-1009`, and let the timeline render:
invoice created, receipt received, approved, paid. Then `/today` to show the Needs your
approval count has dropped and Received this week has gone up.

**Presenter says.**

> The customer gets a confirmation from a pre-approved template, in their language — we
> keep English, Bahasa Melayu and Chinese templates, and no free-form model wording ever
> goes to a customer. The invoice is now Paid, and its timeline shows every step with who
> did it. One approval, about fifteen seconds instead of three minutes, and all of it —
> proposal, approval, payment, invoice change, message — in one database transaction with
> its audit rows.

---

## 2:35–3:15 — Edge cases that genuinely work

Keep this brisk. Three short beats.

### Beat 1: duplicate, and the two kinds of duplicate (2:35–2:55)

**On screen.** `/simulator`. Same customer as the core journey, upload
`003-exact-match.png` again, Send. The panel comes back **Duplicate**, headline
*Already recorded: RM 847.00*, next step *This payment looks like one you already have.
Check it before recording it twice.* That invoice is already Paid, so there is a payment
on the books.

Now the other kind. Switch the user in the role switcher to `Lim Wei Keong · OWNER · Sin
Heng Hardware Trading`, choose `Wong Ah Fook Services` in **Sending as**, and send
`010-exact-match.png` (RM 2,814.00, `INV-1018`). **Leave it unapproved** — do not open
`/approvals`. Then send `032-duplicate.png`, which is a different image of the same
transaction id, `TX4622479024`. The second send comes back **Duplicate** with a different
next step: *The same transaction already arrived and is waiting for a decision (item N).
Handle that one and reject this copy.*

**Presenter says.**

> Same receipt again, and Orbit blocks it and tells you why. But it distinguishes the two
> cases, which matters. The first one is already recorded: there is a payment on the books
> and you must not book it again. This second pair is different — the earlier copy is still
> waiting for a decision, nothing is recorded yet, so the instruction changes: handle the
> one in the inbox and reject this copy. Note these are two different photos of one
> transfer, not the same file twice; the match is on the transaction id. A duplicate is
> always an exception, so it always goes to the owner, never to Finance.

### Beat 2: partial payment (2:55–3:05)

**On screen.** Still signed in as the Owner from the previous beat. `/simulator`, sending
as `Khoo Boon Hwa Resources`, upload `016-partial-payment.png` (RM 297.00 against
`INV-1029`, which is open for RM 595.00). Send. Badges: **Partial Payment**,
**Confidence 60%**, **OWNER must approve**. Open `/approvals`, read the headline *Part
payment of RM 297.00 for INV-1029* and the remaining balance, approve. Jump to `/ledger`,
filter **Partial**, and show `INV-1029` with its reduced outstanding.

**Presenter says.**

> Two hundred and ninety-seven ringgit against a five hundred and ninety-five ringgit
> invoice. Orbit does not force it to fit. The amount signal is worth nothing here, so the
> score is only sixty, and anything below ninety goes to the owner rather than Finance —
> the reference, the payer name and the phone still identify the invoice, so it is not a
> mystery, just not a clean settlement. It records a part payment, leaves the invoice partly
> paid with the remaining balance, and the customer's confirmation says what is still
> outstanding instead of thanking them for settling.

### Beat 3: low confidence goes to a human (3:05–3:15)

**On screen.** `/simulator`. Sending as `Ooi Ah Lek Trading`, upload `040-blurry.png`
(RM 1,500.84 against `INV-1019`). Send. Badges: **Low Confidence**, **OWNER must
approve**. Open `/approvals`, show the blurry image beside the fields, the headline
*RM 1,500.84 needs checking by eye against INV-1019*, the **Needs human** label, and the
amber line *Some details on the image are hard to read, please verify them*. Do not
approve it; leave it sitting in the inbox.

**Presenter says.**

> This receipt is blurry. The per-field confidence on the amount is point five four, below
> our threshold, so Orbit refuses to guess. It labels it Needs human whatever the match
> score says, routes it to the owner rather than Finance, puts the image right next to the
> fields it is unsure about, and tells you in plain words that some details are hard to
> read. I am going to leave it sitting there, because the honest answer to a bad photo is to
> ask a person.

---

## 3:15–3:45 — People stay in control

### Sales is refused (3:15–3:28)

**On screen.** Role switcher, top right, choose `Ravi Chandran · SALES · Sin Heng
Hardware Trading`. The badge next to it changes to **SALES**. Go to `/approvals`. The
grey note under the buttons: *Your role cannot approve payments. The buttons stay here so
you can see what the server says, and the attempt is written to the audit log.* Press
**Approve** anyway. The error from the server appears and the card stays put. If the
browser devtools network tab is already open on a second monitor, show the **403**.

**Presenter says.**

> The login is simulated — there is no real identity provider here — but the permissions
> are not. I am now Ravi, who is Sales. He can see the inbox. We deliberately leave the
> Approve button on screen so you can watch the server refuse it. HTTP 403. The card does
> not move, nothing is recorded, and the attempt itself is written to the audit log.

### The audit chain, and breaking it on camera (3:28–3:45)

**On screen.** `/audit`. Filter **USER** and point at the `APPROVAL_DENIED` row that
Ravi just produced. Press **Verify integrity** — green: *Chain intact — N rows checked.*
Note the id of one row on screen, say the `PAYMENT_RECORDED` row from the core journey.

Cut to a terminal and type, visibly, one line (substitute the id you just read):

```sql
UPDATE audit_log SET actor_id = '99' WHERE id = 42;
```

Run as either of these, whichever is on the machine:

```bash
sqlite3 backend/orbit.db "UPDATE audit_log SET actor_id = '99' WHERE id = 42;"
```

```bash
cd backend && ../.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('orbit.db'); c.execute(\"UPDATE audit_log SET actor_id='99' WHERE id=42\"); c.commit()"
```

Back to `/audit`, press **Verify integrity** again — red: *Chain broken at row 42. A row
was changed after it was written. row contents do not match the stored hash.* Press
**Export .jsonl** to show the chain can be re-checked by anyone, outside Orbit.

Verification is scoped to the signed-in tenant, so tamper with a row belonging to the
tenant you are signed in as — any row from the demo you just shot — and switch back to
that tenant before pressing Verify. Both SQL lines match the live schema: `audit_log` has
`id`, `tenant_id`, `actor_type`, `actor_id`, `action`, `entity_type`, `entity_id`,
`before_json`, `after_json`, `created_at`, `hash_prev`, `hash_self`, with `actor_id`,
`before_json` and `after_json` all stored as text.

**Presenter says.**

> Every state change in Orbit writes an audit row in the same transaction as the change,
> and each row carries the hash of the row before it, one chain per business. Verify: chain
> intact. Now watch. I am going to edit one row directly in SQLite, behind the
> application's back — the application has no update or delete path for this table at all,
> so this is the only way to do it. Change who the actor was on row forty-two. Verify
> again: broken at row forty-two, and it names the row. You can export the whole chain as
> JSON Lines and re-verify it yourself without trusting our screen.

> **Shooting note.** This tamper is permanent for that database. Do it last, or re-seed
> afterwards with `python -m seed.generate_data --reset` (which also clears the approvals
> you did earlier). A more vivid variant, if you prefer to change money rather than a
> person, is `UPDATE audit_log SET after_json = replace(after_json,
> '"amount_sen":84700', '"amount_sen":8470000') WHERE id = 42;` — the stored JSON is
> canonical with no spaces, so the literal must be written exactly like that, and the row
> must be the `PAYMENT_RECORDED` row for the RM 847.00 payment. The `actor_id` line above
> is the safer one to type on camera because it does not depend on the row's text.

---

## 3:45–4:05 — Chasing

**On screen.** `/chasing`. Press **Run now**. Drafts appear with message previews. Scroll
the **Skipped, and why** card so the guard reasons are readable. Toggle one customer off
with the per-customer button. Press the batch approve button. Then scroll to **Owner tasks
— please call, do not message**.

**Presenter says.**

> The other half of the evening is chasing. Orbit drafts reminders on a fixed ladder:
> three days before due, one day after, seven days after. It skips a customer if a payment
> of theirs is waiting for approval, if they are disputed or promised to pay, if we messaged
> them in the last three days, or if it is outside quiet hours — and it shows every skip and
> the reason. Nothing sends until a human approves the batch, and I can drop anyone from it.
> At fourteen days it stops messaging and tells the owner to phone instead. There is no
> scheduler in this build: Run now drives the ladder, deliberately, for the demo.

---

## 4:05–4:42 — The Orbyte connector, live, and the numbers

**On screen.** Three things, in this order. Shoot this on the built single-URL deployment
so `/docs` and the dashboard share the session cookie.

1. `/docs`, scrolled to **GET /api/orbyte/status**. Press **Try it out**, then
   **Execute**, and hold on the response body long enough to read it. Point the cursor at,
   in order: `"connector": "MockOrbyteConnector"`, the `reads_now` block (tenant name,
   users, customers, open invoices, outstanding), and `assumed_interface` — four GETs
   (tenant, users, customers, open invoices) and three POSTs (payments, activity log,
   notifications). Then at `what_stays_in_orbit`.
2. The role switcher, top right. Open it so all nine users across the three tenants are
   visible, switch to `Goh Chin Hoe · OWNER · Cahaya Tuition Centre`, let `/today` reload
   with that tenant's own numbers, then go back to `/docs` and **Execute** the same
   endpoint again. Same code, different tenant name and different counts in `reads_now`.
3. Optional, only if there are seconds left: **GET /api/orbyte/preview** executed once, to
   show the raw hub records with `"simulated": true` on every one. Cut this first if the
   segment is running long.

**Presenter says.**

> Orbit is an Orbyte module, and the connector is on the live path, not decoration. This
> is Orbit asking the hub seam what it can see, right now. The class answering is
> MockOrbyteConnector: four reads — company, users and roles, customers, open invoices —
> and three writes, including a payment record on every approval with an idempotency key,
> so a retry cannot double-record. Every receipt you just watched was scored against
> invoices and customer data fetched through this interface. The mock is here because
> research found no public Orbyte API or sandbox, so these seven endpoints are our
> assumption and every value comes back tagged simulated. A real HTTP connector implements
> the same interface and nothing else changes.

> Now the reuse. I switch to a tuition centre, same build, and the same code serves a
> different SME with its own numbers. Three tenants, nine users, seventy-five customers,
> eighty invoices, all synthetic, every query scoped by tenant. Forty tests pass. On fifty
> labelled receipts the decision path gets forty-seven right, ninety-four percent, and
> extraction is a hundred percent only by construction, because the mock reads the label
> file — [accuracy.md](accuracy.md) says exactly that.

> **Shooting note.** Keep this to 37 seconds. The two `Execute` presses and the tenant
> switch are the whole shot; do not also open `backend/app/connectors/orbyte.py` in the
> editor, which is what an earlier version of this script did. If you want the source on
> screen, put it in the pitch deck. Two points that fit only if you have the breath, and
> are worth cutting first: `what_stays_in_orbit` — the keyed phone hash, receipt images,
> extractions and the audit chain never leave Orbit — and `POST /v1/receipts/analyze`, the
> reusable building block for any other Orbyte module, image in, fields and candidates
> out.

---

## 4:42–5:00 — Hardest risk and fallback

**On screen.** The `/simulator` screen again with the amber *Simulated channel* note, held
still. Optionally end on `/today`, and let the footer that sits on every screen be
readable: *Synthetic data only. The WhatsApp
channel, the Orbyte hub API and the login are simulated. Orbit records payments that
already happened and never moves money.*

**Presenter says.**

> Our hardest risk is access to the WhatsApp Business API. The Cloud API sender is written,
> four settings from live, but with no Meta business account it has never run against Meta
> and I will not claim it works. Verification and template approval are on Meta's timetable,
> and our chase reminders would need approved templates we have not built. The fallback is
> what you have been watching: the same webhook payload shape, so the matching, the approval
> and the audit log are real and only the transport is stubbed. Second risk is accuracy on
> real bank and wallet layouts; the mitigation is structural — per-field confidence, low
> confidence to a human, approval before anything is recorded, the model swappable behind
> one interface. Orbit never moves money. It records payments that already happened.
> Thank you.

---

## Shot list: prepare before you record

1. **Reset to a clean, known state.**
   ```bash
   cd backend
   ../.venv/Scripts/python.exe -m seed.generate_data --reset
   ../.venv/Scripts/python.exe -m seed.generate_receipts
   ```
   The images land in `backend/seed/receipts/` and are gitignored; the labels in
   `backend/seed/ground_truth.csv` are committed.
2. **Build for one URL, and shoot that.** `cd frontend && npm run build`, then run
   `uvicorn app.main:app` from `backend` and use that single address for everything,
   including `/docs`. Development mode (`uvicorn app.main:app --reload` plus `npm run dev`,
   dashboard on `localhost:3000`, `/docs` on `localhost:8000`) works for every segment
   except the Orbyte one: there the session cookie does not reach `/docs`, so
   `/api/orbyte/status` answers as the first Owner in the database and the tenant switch
   does not show.
3. **Confirm `LLM_PROVIDER=mock`** in `.env`. The mock looks up answers by image SHA-256,
   so the demo needs no network and gives the same result every take.
4. **Only upload images from `backend/seed/receipts/`.** The mock matches on SHA-256; any
   other image is treated as unreadable and routed to a human as low confidence, which is
   correct behaviour but not the shot you want.
5. **Have these five files ready in the file picker**, in order of use:

   | File | Amount | Invoice | Customer | Used for |
   |---|---|---|---|---|
   | `003-exact-match.png` | RM 847.00 | INV-1009 | Khoo Boon Hwa Mini Market | core journey, then the already-recorded duplicate |
   | `010-exact-match.png` | RM 2,814.00 | INV-1018 | Wong Ah Fook Services | over the RM 2,000 Finance limit, so it routes to the Owner; left unapproved |
   | `032-duplicate.png` | RM 2,814.00 | INV-1018 | Wong Ah Fook Services | the waiting-copy duplicate: a second photo of the same transaction id, `TX4622479024` |
   | `016-partial-payment.png` | RM 297.00 | INV-1029, open for RM 595.00 | Khoo Boon Hwa Resources | part payment |
   | `040-blurry.png` | RM 1,500.84 | INV-1019 | Ooi Ah Lek Trading | low confidence, amount confidence 0.54 |

   Use `040-blurry.png` and not `039-blurry.png` for the low-confidence beat: 039 is the
   same customer and the same amount as `010-exact-match.png` within twenty-four hours, so
   after the duplicate beat it is classified as a duplicate, which is correct behaviour but
   the wrong shot.
6. **Know your users.** Tenant 1 is Sin Heng Hardware Trading: `Lim Wei Keong` OWNER
   (unlimited), `Nurul Aisyah Binti Rahim` FINANCE (capped at RM 2,000), `Ravi Chandran`
   SALES. Other tenants: `Siti Zubaidah Binti Hassan` (Roti Lima Bakery Supplies),
   `Goh Chin Hoe` (Cahaya Tuition Centre).
7. **Role order.** Start as `Nurul Aisyah Binti Rahim` (FINANCE), so the 0:50–2:35
   approval is done by the role the proposal was actually routed to. Switch to
   `Lim Wei Keong` (OWNER) for the rest of the edge cases — the RM 2,814 pair, the part
   payment and the blurry receipt all route to the Owner — then to `Ravi Chandran` (SALES)
   for the 403, and back to an OWNER or FINANCE user for the audit and Orbyte segments.
   The last switch of the shoot is to `Goh Chin Hoe` (Cahaya Tuition Centre), for the
   reuse shot.
8. **Make sure the chasing ladder has something to draft.** Press **Run now** on
   `/chasing` once before recording. If the drafts list is empty, nothing is due today;
   either shoot the Skipped card and the owner-call tasks instead, or shift due dates in
   the seed and re-run it.
9. **Note the audit row id you will tamper with** before you start the terminal shot, and
   remember the tamper is irreversible for that database file. Pick a row belonging to the
   tenant you will be signed in as when you press Verify; verification is per tenant.
10. **Dry-run the two `/docs` calls.** Press **Try it out** and **Execute** on
    `GET /api/orbyte/status` once before recording, so the response is already expanded and
    you know how far to scroll to reach `assumed_interface`.
11. **Stills to prepare:** the section 6.1 architecture diagram with the five steps
    highlighted, and the burned-in caption *Synthetic data. Simulated WhatsApp channel.*
    for the opening scene.
12. **Record a backup take of 0:50–2:35** and keep it to hand, in case the live segment
    misbehaves on the day.
13. **Audio and framing:** one window at a time, browser zoom around 110% so the
    confidence bar and the Why-we-think-so lines are legible at 1080p, and no real names,
    numbers or receipts anywhere in frame.

---

## Honesty checklist

The presenter must say, out loud and in the same sentence as the thing itself, that the
following are simulated or not yet built: the demo runs on the built-in WhatsApp
simulator, and while the Cloud API sender is written and switches on with four settings,
it is **unverified against Meta** because there is no Meta business account — only the
transport is stubbed, the webhook payload shape is the real one, and live chase reminders
would additionally need approved template messages that do not exist yet; the
login and role switcher are a **simulated** session, though the permissions they enforce
are real server-side checks; the Orbyte hub API is a **mock we wrote ourselves** against
endpoints we assumed, and every value it returns is tagged simulated; all data is
**synthetic** — three tenants, nine users, seventy-five customers, eighty invoices and
fifty generated receipt images, no real people, phone numbers, bank accounts or receipts;
the extractor is running in **mock mode**, which reads labelled answers by image hash, so
the hundred percent extraction figure is true by construction and is **not** a measurement
of a model; there is **no scheduler**, the chase ladder is driven by a Run now button;
Orbit **does not detect forged receipts** and must not be described as fraud detection —
it flags duplicates and odd fields and keeps the image for the owner to check against
their bank app; Orbit **never moves money**, it records payments that already happened;
and the time and cost figures quoted are **targets against an assumed manual baseline**,
not a measured pilot. Finally, say what does not exist yet: no live WhatsApp connection,
no Replit deployment, no database migrations, and the pitch deck is separate from this
video.
