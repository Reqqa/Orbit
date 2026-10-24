    # Orbit: WhatsApp Payment Reconciliation & Automated Chasing for the Orbyte Hub
### S.D.C. Hackathon 2026, Domain 2: Orbyte Smart SME Challenge (Alpha Red Solutions)

> **Naming:** the product is **Orbit**. It is a module that plugs into the **Orbyte** business hub
> (Orbyte is the host platform, not us). Tagline to use consistently so judges can tell them apart:
> **"Orbit, payment reconciliation for the Orbyte hub."**

---

## 0. How to use this spec with Claude Code

- Standing rules live in `CLAUDE.md` in the repo root (Claude Code reads it automatically). Section 20 lists them.
- Build one step at a time, following the step list in Section 14. Each step has a "done when" check.
- Where this spec is ambiguous, pick the simplest option that keeps the demo reliable.
- Never fake results. If something is simulated (WhatsApp, Orbyte API, login), label it clearly in the UI, API and README.
- Changes to this spec are recorded in the Decision Log (Section 21).

---

## 1. One-paragraph pitch

Malaysian micro and small businesses run on WhatsApp. Customers pay by DuitNow, bank
transfer or e-wallet and then send a screenshot of the receipt on WhatsApp. The owner
(often at night) opens each chat, squints at the screenshot, checks the bank app,
ticks a spreadsheet, and then chases late payers by hand. **Orbit** turns that
WhatsApp thread into a controlled workflow: it reads each incoming payment proof,
matches it to the right open invoice, explains how confident it is, asks the owner to
approve with one tap, records the payment automatically, and drafts polite reminders for
overdue invoices (sent only after owner approval). Every action is permission-checked and
written to an audit log. It is built as a reusable module on the Orbyte business hub, so
it can serve many SMEs without each one setting up a custom system.

**We never move money.** Orbit records and reconciles payments that already happened
(preparatory bookkeeping), which keeps us inside the "no processing real payments" boundary.

---

## 2. Rubric strategy (what judges score, and where we win it)

| Criterion | Weight | What judges want | How Orbit hits it |
|---|---|---|---|
| Innovation & Creativity | 30% | Specific real pain point, original product, AI only where it adds value, not a re-skinned chatbot, not HR/admin | Pain point is concrete: "owner manually matches WhatsApp receipt screenshots to invoices and chases late payers every evening". AI is used for exactly one thing (reading messy receipt images and noisy messages). Matching, scoring, approval, chasing schedules are deterministic rules. This is a workflow product, not a chat UI. Finance/receivables is a new capability, not HR/admin. |
| Problem-Solution Fit | 25% | Removes one recurring burden, accurate and consistent, easy to learn, people in control (permissions + approval + log), fits Orbyte hub, reusable, within boundaries | One burden: payment reconciliation + chasing. Role-based permissions (Owner / Finance staff / Sales staff). Approval gate before any consequential action. Activity log. Orbyte connector layer. Multi-tenant. Zero-training because owner approves inside WhatsApp itself. |
| Feasibility of Build | 25% | Full journey live (trigger, data, decision, approval, outcome), GitHub repo, synthetic data, own API assumptions, names hardest risk with fallback, no dependency on live Orbyte | Journey runs live end to end. Built-in WhatsApp simulator means demo never depends on Meta approval. Mock Orbyte API we define ourselves. Risk register with fallbacks (Section 12). |
| Clarity of Proposal | 20% | Problem, approach, expected outcome with measurable benefit, easy to explain back, follows format/length | One-sentence problem, five-step approach, quantified outcome (Section 11), simple diagram, template-compliant. |

**Judging tip baked into the plan:** the preliminary round needs the single most important
feature running live. Ours is: **receipt in WhatsApp -> extracted -> matched -> owner approves -> ledger updated -> dashboard shows it, with audit log.** Chasing is the second feature (demo it if time allows, otherwise present as working-in-repo plus roadmap).

---

## 3. Rules and boundaries checklist (must stay inside)

- [x] Genuine SME need: finance / receivables / customer service.
- [x] Adds a distinct capability, not Orbyte's existing HR/admin functions.
- [x] Fits the hub: consumes Orbyte company, user, role, customer and invoice data via a connector; writes back payment records and activity logs.
- [x] Reusable: multi-tenant, configurable rules, works for any SME that invoices on credit (trading, F&B suppliers, tuition centres, repair shops, wholesalers).
- [x] Focus: ONE use case demoed. Everything else is roadmap.
- [x] Synthetic data only. No real receipts, names, phone numbers, bank accounts.
- [x] Out of scope: we do not process real payments, submit statutory filings (e.g. no LHDN e-invoice submission), or give legal/financial advice. Reminders are templated courtesy messages, not legal demands.
- [x] PDPA explanation included (Section 10).
- [x] Simulated login/RBAC is explicitly allowed.

---

## 4. Users and roles

| Role | Who | Can do |
|---|---|---|
| **Owner** | Business owner | View everything; approve/reject matches; approve chase batches; manage settings; view audit log |
| **Finance staff** | Bookkeeper/admin | View ledger; approve matches up to a configurable amount (e.g. RM 2,000); cannot change settings |
| **Sales staff** | Salesperson | View only their own customers' invoices; cannot approve anything; can see whether their customer has paid |
| **Customer** (WhatsApp only) | Payer | Sends receipt; receives acknowledgement and reminders; no dashboard access |

Approval rule example (configurable per tenant): amount <= RM 2,000 and confidence >= 90%
may be approved by Finance; anything above, or any exception type, needs Owner. This is
the visible "people stay in control" feature.

---

## 5. The core journey (maps 1:1 to the brief's five steps)

```
 1 TRIGGER            2 CONNECTED DATA         3 DECISION LOGIC
 Customer sends       Pull open invoices,      AI extracts fields from image/text.
 receipt image or     customer record, past    Rules engine scores matches and
 text on WhatsApp  -> payments, tenant     -> classifies the case.
                      settings from Orbyte
                      connector
                                  |
                                  v
 5 VISIBLE OUTCOME    <-  4 HUMAN APPROVAL  <-  Recommendation + explanation
 Invoice marked paid      Owner/Finance taps     "Matches INV-1042, RM 850.00,
 Ledger updated           Approve / Reject /     ref matches, name 96% similar,
 Customer notified        Edit in WhatsApp       confidence 94%"
 Dashboard + audit log    or dashboard
```

### 5.1 Detailed flow (receipt reconciliation, the MUST-DEMO feature)

1. **Trigger.** Customer (e.g. "Ahmad, Kedai Runcit Maju") sends a bank transfer screenshot to the business's WhatsApp number.
2. **Webhook.** WhatsApp Cloud API (or the built-in simulator, same payload shape) posts the message to `/webhooks/whatsapp`. Backend verifies signature, ignores duplicates by `wa_message_id` (Meta retries deliveries), stores the message (media reference only), identifies tenant by receiving number, identifies customer by sender phone number (keyed HMAC lookup). Returns 200 immediately; processing continues in a background task.
3. **Extraction (AI, only here).** Vision model returns strict JSON: `amount, currency, date, time, payer_name, payee_name, bank_or_wallet, reference_text, transaction_id, confidence per field, is_receipt (bool)`. If `is_receipt=false`, reply with a friendly "please send your payment receipt" and log it.
4. **Matching (rules, deterministic).** Score each open invoice of that customer (and, if customer unknown, of the tenant) using the weighted scorecard in Section 7. Output a ranked list.
5. **Classification.** One of: `EXACT_MATCH`, `PARTIAL_PAYMENT`, `OVERPAYMENT`, `MULTI_INVOICE`, `DUPLICATE`, `UNMATCHED`, `LOW_CONFIDENCE`, `NOT_A_RECEIPT`.
6. **Recommendation + explanation.** Template-generated explanation (not free LLM text) listing which signals matched and which are missing. Missing information is explicitly handed to a human ("Reference number not found, please confirm").
7. **Approval request.** Owner/Finance receives a WhatsApp interactive message with buttons: **Approve / Reject / Review on dashboard**. The same item appears in the dashboard "Approval inbox". Role and amount limit checked server-side.
8. **Outcome.** On approve (one DB transaction): create `payment` record, allocate to invoice(s), update invoice status (`PAID`, `PARTIAL`), update customer ledger balance, write audit entries; then send confirmation to customer ("Thanks Ahmad, RM 850.00 received for INV-1042"). On reject: ask customer for clarification, log reason.
9. **Dashboard.** Live KPIs and tables update (Section 9).

### 5.2 Second flow (automated chasing, build if time allows)

1. **Trigger (scheduled).** Daily job at a tenant-configured time finds overdue invoices. A "Run now" button exists for the demo.
2. **Data.** Invoice, customer, payment history, last reminder sent, customer's preferred language (BM/EN/ZH).
3. **Decision (rules).** Escalation ladder: Day -3 gentle heads-up, Day +1 polite reminder, Day +7 firm reminder, Day +14 flag to owner for personal follow-up (no automated message). Skips customers with a pending approval, a promised-pay date, or a disputed flag. Max 1 message per customer per 3 days.
4. **Draft.** Fill an approved message template (no free-form LLM text; see Section 7.4).
5. **Approval.** Owner approves a batch ("Send 6 reminders") with a preview.
6. **Outcome.** Messages sent via WhatsApp template messages; statuses tracked (sent/delivered/read); customer replies with a receipt re-enter flow 5.1. Everything logged.

---

## 6. System architecture

### 6.1 Component diagram

```
                +-----------------------------+
                |  WhatsApp (customers, owner)|
                +--------------+--------------+
                               |  Cloud API (webhook in / messages out)
                               v
+---------------------------------------------------------------------+
|                          ORBIT BACKEND (FastAPI)                    |
|                                                                     |
|  Webhook Gateway --> Message Router --> Ingestion Service           |
|                                             |                       |
|                                             v                       |
|                                   Extraction Service (AI)           |
|                                             |                       |
|                                             v                       |
|   Matching Engine (rules) <--> Orbyte Connector (adapter)           |
|                |                      |                             |
|                v                      v                             |
|   Approval Service (RBAC)        Mock Orbyte API (synthetic data)   |
|                |                                                    |
|                v                                                    |
|   Ledger Service --> Notification Service --> Sender interface      |
|                |                     (SimulatorSender / CloudApiSender)
|                v                                                    |
|   Audit Log (append-only, hash-chained)   Scheduler (chasing jobs)  |
+-------------------+-------------------------------------------------+
                    |
          +---------+----------+
          |   SQLite (one file) |
          +---------+----------+
                    |
                    v
        +-----------------------------+
        | React Dashboard (Vite)      |
        | Owner / Finance / Sales view|
        +-----------------------------+

   WhatsApp Simulator (built into dashboard) can replace the real WhatsApp
   channel for demo reliability. Same webhook payload format.
```

### 6.2 Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Fast to build, great for AI + webhooks, auto API docs at `/docs` (good for judges) |
| DB | SQLite via SQLAlchemy 2.0 | Single file, zero setup, real transactions (needed for atomic approvals) |
| Frontend | Next.js (App Router, static export) + React + Tailwind | Real routes per screen, one URL in production (FastAPI serves the export), no Node process to deploy. Components and KPI bars are hand-written, so no component or chart library. |
| AI extraction | Claude vision with strict JSON output, behind an `Extractor` interface | Best accuracy on messy screenshots; swappable; a labelled mock extractor for development |
| Optional self-host | OCR/vision model on RunPod behind the same interface | "Proof of RunPod utilization" and a PDPA data-residency story. Only claim it if truly used. |
| Fuzzy matching | `rapidfuzz` | Payer name similarity |
| Scheduler | APScheduler | Daily chasing job |
| Messaging | WhatsApp Business Cloud API (Meta) + built-in simulator | Real integration with safe fallback |
| Auth | Simulated: role switcher (Owner/Finance/Sales) with signed session cookie | Allowed by brief |
| Hosting | Replit (Deployments for public URL); FastAPI serves the built frontend so there is one URL | Required proof of Replit usage |

### 6.3 Key design principles

1. **AI only where it adds value.** AI = reading unstructured receipt images. Everything consequential (match scoring, classification, approval limits, chase schedule) is deterministic.
2. **Human approval before any consequential action.** Recording a payment, sending a reminder batch, and writing off/adjusting are all gated.
3. **Explainable by default.** Every recommendation shows its evidence.
4. **Adapter pattern for Orbyte.** All hub data goes through `OrbyteConnector`. MVP ships `MockOrbyteConnector`; a real one would implement the same interface. This is our Orbyte-fit and reuse argument, and it removes dependency on live access.
5. **Multi-tenant from day one.** Every table has `tenant_id`; every query is scoped.
6. **Append-only audit log.** No update/delete endpoints for audit. Each audit row is written in the same transaction as the change it records.
7. **Money is integer sen.** RM 850.00 is stored as `85000`. No floats anywhere in money handling.

---

## 7. Decision logic details

### 7.1 Extraction contract (LLM output, strict JSON)

```json
{
  "is_payment_receipt": true,
  "amount": 850.00,
  "currency": "MYR",
  "transaction_datetime": "2026-10-21T14:32:00+08:00",
  "payer_name": "AHMAD BIN ABDULLAH",
  "payee_name": "MAJU TRADING SDN BHD",
  "channel": "DuitNow Transfer",
  "bank_or_wallet": "Generic Bank",
  "reference_text": "INV1042",
  "transaction_id": "TXN20261021XXXXXXXX",
  "field_confidence": {"amount": 0.99, "date": 0.95, "payer_name": 0.9, "reference_text": 0.8},
  "notes": "reference partially cropped"
}
```

Rules around extraction:
- Validate with Pydantic. Reject/flag if amount missing or non-positive. Convert amount to integer sen immediately after validation.
- Never let the LLM decide the match or approval. It only reads.
- Store the raw extraction JSON alongside the final human-approved values (shows human-in-loop corrections and lets us measure accuracy).
- Cache results by image SHA-256 so demo receipts never depend on a live API call.
- Temperature 0. Retry once on invalid JSON, then fall back to `LOW_CONFIDENCE` human review.

### 7.2 Match scorecard (weights are configurable per tenant)

| Signal | Weight | Logic |
|---|---|---|
| Amount equals invoice outstanding | 40 | Exact = 40; within 5 sen = 35; equals a known instalment = 25; else 0 |
| Reference contains invoice no. | 25 | Normalised substring match (strip spaces, dashes, case) |
| Payer name similarity to customer name or known aliases | 15 | `rapidfuzz` token_set_ratio scaled |
| Sender phone matches customer on file | 10 | HMAC compare |
| Date plausibility | 5 | After invoice date, not future |
| Single open invoice for customer | 5 | Bonus for unambiguous case |

`confidence = sum(weights)` (0-100). Thresholds (configurable): >= 90 "Strong match", 70-89 "Likely, please check", < 70 "Needs human".

### 7.3 Classification rules

| Case | Condition | Action |
|---|---|---|
| EXACT_MATCH | Top score >= 90, amount equals outstanding | Offer one-tap approve |
| PARTIAL_PAYMENT | Amount < outstanding, strong other signals | Approve as partial, show remaining balance |
| OVERPAYMENT | Amount > outstanding | Flag; owner decides (credit on account vs refund note). No refunds executed. |
| MULTI_INVOICE | Amount equals sum of 2+ open invoices of same customer | Propose allocation oldest first; owner confirms |
| DUPLICATE | Same `transaction_id`, or same amount+payer+date within 24h already recorded | Block auto-recording, alert user |
| UNMATCHED | No candidate >= 40 | Ask owner to pick customer/invoice manually |
| LOW_CONFIDENCE | Key field confidence < 0.7 | Human review with image shown next to extracted fields |
| NOT_A_RECEIPT | `is_payment_receipt=false` | Polite reply; no record |

Fraud note: we flag duplicates and missing/odd fields, and always keep the original image for the owner to verify against their bank app. We **do not** claim to detect forged screenshots; the owner remains the final check ("bank statement cross-check" is a roadmap feature via CSV upload).

### 7.4 Chasing ladder (rules, configurable)

| Offset from due date | Action | Approval |
|---|---|---|
| -3 days | Friendly heads-up (optional per tenant) | Batch approval |
| +1 day | Polite reminder with invoice summary | Batch approval |
| +7 days | Firmer reminder | Batch approval |
| +14 days | No auto message; create "call this customer" task for owner | n/a |

Guards: skip if payment pending approval, if customer flagged "disputed" or "promised to pay on date X", if a reminder was sent in the last 3 days, or outside quiet hours (before 9am / after 8pm local). Messages use pre-approved templates (BM / EN / ZH) with variables. No free-form LLM wording in reminders.

---

## 8. Data model (synthetic, multi-tenant)

Conventions: all money columns are integer sen (`*_sen`). Phone numbers are stored as two
columns: `*_hmac` (keyed HMAC, indexed, for lookup) and `*_enc` (encrypted, used only to send replies).

```
tenants(id, name, whatsapp_number, timezone, settings_json)
users(id, tenant_id, name, role[OWNER|FINANCE|SALES], phone_hmac, phone_enc, approval_limit_sen)
customers(id, tenant_id, name, aliases[], phone_hmac, phone_enc, language, assigned_sales_user_id, flags[])
invoices(id, tenant_id, customer_id, invoice_no, issue_date, due_date, total_sen, outstanding_sen,
         status[OPEN|PARTIAL|PAID|VOID])                     -- unique (tenant_id, invoice_no)
whatsapp_messages(id, tenant_id, wa_message_id UNIQUE, direction, from_hmac, type, media_ref, text,
                  received_at, status, simulated)
extractions(id, message_id, raw_json, model_name, image_sha256, created_at)
match_proposals(id, tenant_id, message_id, extraction_id, customer_id, classification, top_candidates_json,
                confidence, explanation_json, status[PENDING|APPROVED|REJECTED|EXPIRED],
                requested_approver_role, decided_by, decided_at, decision_note, created_at)
payments(id, tenant_id, customer_id, amount_sen, paid_at, channel, reference, transaction_id,
         proposal_id UNIQUE, recorded_by, created_at)
payment_allocations(id, payment_id, invoice_id, amount_sen)
reminders(id, tenant_id, invoice_id, rung, template_id, status[DRAFT|APPROVED|SENT|DELIVERED|READ|FAILED],
          approved_by, sent_at)
audit_log(id, tenant_id, actor_type[USER|SYSTEM|AI|CUSTOMER], actor_id, action, entity_type, entity_id,
          before_json, after_json, created_at, hash_prev, hash_self UNIQUE)   -- append-only, hash-chained
```

Hash-chained audit log (each row stores the hash of the previous row) is a cheap but impressive "tamper-evident" detail for the governance criterion. An "Export audit log (.jsonl)" button lets judges verify the chain independently.

### 8.1 Synthetic dataset to generate (important for demo)

- 3 tenants (a hardware trader, a bakery supplier, a tuition centre) to prove reusability. Demo mainly on tenant 1.
- 25 customers per tenant, with Malay, Chinese and Indian names, some with aliases (e.g. "Ah Seng" vs "Tan Ah Seng Enterprise").
- 80 invoices with mixed statuses and due dates (some overdue by 1, 7, 14+ days).
- **A test set of ~50 synthetic receipt images** generated by script (Pillow, generic layouts with fictional bank names, to avoid trademark and real-data issues). Start with 10, grow to 50. Include deliberately tricky ones: cropped reference, blurry, partial payment, overpayment, duplicate, two-invoice payment, non-receipt photo, wrong-amount, BM text.
- A labelled `ground_truth.csv` so we can report real extraction/match accuracy honestly.

---

## 9. Dashboard and UX (easy to learn without training)

Design rule: a new user should complete the core task in under 60 seconds with zero instructions.

**Screens**
1. **Today (home).** Three big cards: "Needs your approval (n)", "Overdue (RM x)", "Received this week (RM y)". Big primary button: "Review approvals".
2. **Approval inbox.** Card per item: receipt image on the left, extracted fields on the right, suggested invoice, confidence bar, plain-language "Why we think so", buttons Approve / Edit / Reject. Missing info highlighted in amber.
3. **Ledger & invoices.** Filterable table; click an invoice to see timeline (invoice created, reminder sent, receipt received, approved, paid).
4. **Chasing.** Tomorrow's reminder batch with message previews, tone, per-customer skip toggle, "Approve batch".
5. **Customers.** Balance, last payment, reminder history.
6. **Audit log.** Searchable, shows who/what/when, AI vs human actions colour-coded, "Verify integrity" button for the hash chain, "Export .jsonl" button.
7. **Settings (Owner only).** Approval limits, thresholds, chase ladder, quiet hours, language templates.
8. **WhatsApp Simulator (demo mode).** A phone-style chat panel: pick a customer, upload a receipt, watch the bot reply; second panel shows the owner's phone with approval buttons. Clearly labelled "Simulated channel".
9. **Role switcher (demo mode).** Top-right dropdown: Owner / Finance / Sales, to show permissions live. Sales sees a restricted view and gets "You don't have permission" if they attempt to approve (and the attempt is logged).

**Ease-of-learning tactics (state these in the pitch):** approval happens inside WhatsApp, which the owner already uses; one-tap actions; plain-language explanations; empty states with guidance; BM/EN/ZH message templates; no setup wizard beyond uploading an invoice list (CSV) or connecting via Orbyte.

**KPI strip (proof of benefit, shown on dashboard):** receipts processed, average handling time (system vs estimated manual baseline), auto-match rate, human-correction rate, days sales outstanding (DSO) trend, reminders sent vs paid within 7 days.

---

## 10. Governance, privacy and PDPA

| PDPA principle | How a real deployment handles it |
|---|---|
| General principle (consent) | Tenant obtains customer consent for WhatsApp communication and payment record processing; opt-out keyword ("STOP") respected and stored |
| Notice and Choice | First-contact message states purpose and who processes data |
| Disclosure | Data shared only with the Orbyte tenant, the LLM provider (under data processing terms), and WhatsApp/Meta as channel; no resale |
| Security | Encryption in transit and at rest; phone numbers stored as a keyed HMAC for lookup plus an encrypted copy used only for replies (plain hashes of phone numbers are brute-forceable, so we use a secret key); receipt images in private storage with signed URLs; webhook signature verification; RBAC; hash-chained audit log |
| Retention | Receipt images auto-deleted after configurable period (e.g. 90 days) once recorded; payment records kept per business/tax obligations |
| Data Integrity | Human review of low-confidence extractions; users can correct records |
| Access | Customers can request their records via the business; export endpoint per customer |
| Data minimisation | Only fields needed for reconciliation extracted; account numbers masked (store last 4 only) |
| Cross-border (if using overseas LLM) | Disclose; option for self-hosted model (RunPod/in-region) for sensitive tenants |

Also state: MVP uses **only synthetic data**, no real personal or company records.

---

## 11. Business benefit (measurable, honest)

State these as **targets and assumptions** and back them with what we can measure in the demo.

| Metric | Manual baseline (assumption, validate) | With Orbit target |
|---|---|---|
| Time per receipt (open chat, read, check, key in, reply) | 2-4 min | ~15-20 sec (one tap approval) |
| Owner time on reconciliation + chasing per week | 4-8 hours (assumption) | ~1 hour (approvals only) |
| Data entry errors (wrong invoice/amount) | Occurs regularly (unquantified) | Target: > 90% auto-match accuracy on test set, 100% human-confirmed before recording |
| Overdue follow-up consistency | Ad hoc | 100% of overdue invoices touched per ladder, with approval |
| Tasks completed without training | n/a | New user completes first approval in < 60 s (measure with 3-5 testers) |

**Do this to strengthen credibility (cheap, high impact):**
- Run the 50-image synthetic test set and report real extraction and match accuracy (put numbers in the README and deck).
- Time 3-5 friends doing the task manually (spreadsheet + chat) vs with Orbit. Report the result as a small pilot ("n=5, synthetic data").
- If possible, a 10-minute chat with 2-3 real SME owners. Even brief quotes count as real-world validation.

**SDG contribution:** SDG 8 (8.2 productivity via technological upgrading; 8.3 supports growth of micro/small enterprises, better cash flow) and SDG 9 (innovation and digital infrastructure for SMEs). Optional: SDG 12 (less paper) and SDG 10 (low-cost tool for businesses that cannot afford ERP), only if we explain the genuine link.

---

## 12. Risks and fallbacks (judges explicitly look for the "hardest risk")

| Risk | Impact | Mitigation / fallback |
|---|---|---|
| **HARDEST RISK: WhatsApp Business API access** (Meta business verification, number registration, template approval takes time) | Live WhatsApp demo may fail | Primary: Meta Cloud API test number (free sandbox, can message up to 5 verified numbers). Fallback: built-in WhatsApp simulator using identical webhook payloads, so the pipeline code is the same. Always label simulated parts honestly. Pre-record a clip of the real API working if achieved. |
| Receipt extraction accuracy on varied Malaysian bank layouts | Wrong data | Per-field confidence; low confidence routes to human; mandatory approval; measure accuracy on labelled test set; swap model behind interface |
| LLM API latency / outage during demo | Demo stalls | Cache extraction results by image hash; "retry" button; fallback regex/OCR for text-heavy receipts |
| Orbyte API unknown | Integration risk | Adapter pattern + documented assumed endpoints (Section 13); mock implementation |
| Fake or edited receipts | Fraud | Duplicate detection, owner verification against bank, roadmap: bank statement CSV matching. Not claimed as fraud detection |
| Scope creep (the biggest build risk) | Nothing finished | Strict step order (Section 14). Chasing is stretch. |
| Replit resource limits | Slowness | Lightweight stack, SQLite, no heavy local models; RunPod only if needed |

---

## 13. Orbyte fit and reuse

**Positioning:** Orbit is an Orbyte *app module* that turns Orbyte's shared business hub (company, users, roles, customers, invoices) into a receivables workflow.

**Assumed Orbyte interface** (we define these ourselves, as the brief allows):

```
GET  /orbyte/v1/tenants/{id}                 -> company profile, timezone, language
GET  /orbyte/v1/users?tenant={id}            -> users + roles (RBAC source of truth)
GET  /orbyte/v1/customers?tenant={id}        -> customer master data
GET  /orbyte/v1/invoices?status=open         -> open/overdue invoices
POST /orbyte/v1/payments                     -> record payment (idempotency key)
POST /orbyte/v1/activity-log                 -> push audit events to the hub
POST /orbyte/v1/notifications                -> optional in-hub alerts
Webhook: invoice.created, invoice.updated, customer.updated
```

**Why this is stronger than a standalone app:**
- Reuses Orbyte login, profiles and RBAC instead of rebuilding them.
- Reuses customer and invoice data, so no re-entry (accuracy).
- Audit events flow into the hub's shared activity log (governance).
- The same module serves any Orbyte SME with a config change, no custom build.
- Other Orbyte solutions can consume our output ("payment received" events could feed inventory release, e-invoice readiness, cash-flow forecasting).

**Reusable building block:** expose `orbit-core` as a small API: `POST /v1/receipts/analyze` (image in, structured fields + match candidates out). Documented on the auto-generated OpenAPI page.

**Reuse across SMEs (3 tenants in demo data):** wholesale trader (credit terms), tuition centre (monthly fees by parent), catering supplier (weekly invoices).

---

## 14. Build plan (step by step)

Each step is small and ends with a "done when" check. Do not start a step until the previous one passes.

**Foundation**
1. **Skeleton, DB models, health endpoint.** Done when `/docs` and `/api/health` load on Replit and the 12 tables exist in `orbit.db`.
2. **Phone privacy helpers** (HMAC lookup + encryption). Done when a number round-trips through encrypt/decrypt and always gives the same HMAC.
3. **Audit service** (hash chain + verify). Done when a test shows editing any audit row breaks verification.
4. **Seed script** (3 tenants, users with roles, 25 customers each, invoices with mixed due dates). Done when it prints counts and data is visible.
5. **Orbyte connector + simulated login + RBAC.** Done when a test shows Sales gets 403 and the denial is in the audit log.

**Core journey (must demo)**
6. **WhatsApp webhook** (Meta-shaped payloads, duplicate message IDs ignored, tenant/customer identified, background task). Done when posting the same payload twice stores one message.
7. **Synthetic receipts** (10 to start) + `ground_truth.csv`. Done when images open and look like plausible generic receipts.
8. **Extraction service** (interface, labelled mock, Claude vision, validation, cache). Done when one image returns valid JSON.
9. **Matching engine** (pure functions). Done when tests pass for exact, partial, overpayment, multi-invoice.
10. **Classification + explanations.** Done when tests pass for all eight cases.
11. **Proposals + approval routing.** Done when RM 3,000 routes to Owner and RM 500 to Finance.
12. **Approval decision + ledger update + customer confirmation.** Done when one call moves an invoice OPEN -> PAID with a full audit trail.

**Frontend**
13. **React scaffold + role switcher + API client.** Done when the page shows current role and tenant name from the API.
14. **WhatsApp simulator screen** (labelled simulated). Done when uploading a receipt creates a proposal.
15. **Approval inbox.** Done when you can approve end to end from the UI.
16. **Today dashboard + invoice timeline + audit page** (verify + export). Done when an approval visibly updates KPIs and timeline.

**Checkpoint:** run 10 receipts end to end. Record a backup demo video. Preliminary-round requirement met.

**Stretch (decided by deadline)**
17. Real WhatsApp Cloud API (time-boxed 3-4 h; if blocked, keep the simulator).
18. Chasing (scheduler, ladder, batch approval, "Run now" button).
19. Accuracy evaluation on 50 receipts + KPI strip.
20. Submission pack (README, tech tools declaration, deck, video).

Throughout: take Replit workspace screenshots for "Proof of Replit utilization". RunPod only if a model is actually hosted there.

### 14.1 Repo structure

```
orbit/
  LICENSE                      # Apache 2.0 (added via GitHub)
  README.md                    # problem, approach, outcome, run steps, accuracy table, PDPA, risks
  CLAUDE.md                    # standing rules for Claude Code (Section 20)
  TECH_TOOLS_DECLARATION.md    # every tool/model/API/library + where AI assistance was used
  .replit  .gitignore  .env.example
  docs/
    SPEC.md                    # this document
    demo-script.md
    proof/replit-*.png
    proof/runpod-*.png         # only if applicable
  backend/
    requirements.txt
    app/
      main.py  config.py  db.py  models.py
      auth/            (simulated login, rbac.py)
      connectors/      (orbyte_base.py, orbyte_mock.py)
      webhooks/        (whatsapp.py)
      services/        (crypto.py, audit.py, extraction.py, matching.py, classify.py,
                        approval.py, ledger.py, notify.py, chasing.py)
      templates/       (whatsapp messages BM/EN/ZH)
    tests/             (test_matching.py, test_classify.py, test_rbac.py, test_audit_chain.py)
    seed/              (generate_data.py, generate_receipts.py, ground_truth.csv)
  frontend/                    # Next.js dashboard, static export
    package.json  next.config.mjs  postcss.config.mjs  jsconfig.json
    app/                       # one route per screen: today, approvals, ledger,
                               # chasing, customers, audit, simulator, settings
      layout.jsx  globals.css
    components/
      Shell.jsx                # header, nav, role switcher, session context
      Screen.jsx  ui.jsx       # the whole component kit
      pages/                   # the eight screen components
    lib/api.js                 # every backend call
  scripts/ (eval_accuracy.py, replit-start.sh)
```

### 14.2 API endpoints (minimum)

```
POST /webhooks/whatsapp              inbound messages (verify signature)
GET  /webhooks/whatsapp              Meta verification handshake
GET  /api/health
GET  /api/approvals?status=pending
POST /api/approvals/{id}/decision    {decision, note, edits}  (RBAC + limit enforced)
GET  /api/invoices, /api/customers, /api/payments
GET  /api/dashboard/summary
GET  /api/audit?filters   GET /api/audit/verify   GET /api/audit/export.jsonl
GET  /api/chasing/batch/tomorrow    POST /api/chasing/batch/{id}/approve
POST /api/simulator/send            (demo mode only)
POST /v1/receipts/analyze           reusable building block
```

### 14.3 Tests (only these, kept small)

- Matching + classification: exact, partial, overpay, multi-invoice, duplicate, unmatched.
- RBAC: Sales cannot approve; Finance cannot exceed limit; denied attempts are logged.
- Audit: tampering with a row breaks verification.
- No tests for UI, webhook, seed script or anything else. The accuracy eval script is separate (Step 19).

---

## 15. Demo script (target 4:30, max 5:00 for the YouTube Unlisted video)

| Time | Show | Rubric payoff |
|---|---|---|
| 0:00-0:25 | Problem: owner's evening with WhatsApp receipts and spreadsheet (one real-feeling scene, synthetic) | Innovation: specific pain |
| 0:25-0:50 | Solution in one sentence ("Orbit, payment reconciliation for the Orbyte hub") + 5-step diagram | Clarity |
| 0:50-2:40 | **Live core journey:** customer sends receipt in WhatsApp (or simulator) -> extraction -> match explanation -> owner approves with one tap -> customer confirmation -> dashboard updates -> invoice timeline | Feasibility, Problem-Fit |
| 2:40-3:20 | Edge cases: duplicate blocked; partial payment; low-confidence routed to human | Accuracy and consistency |
| 3:20-3:50 | Role switch: Sales cannot approve (attempt logged); audit log + integrity check (tamper a row live, watch verify fail) | People stay in control |
| 3:50-4:15 | Chasing batch preview and approval (or short clip) | Innovation, stretch |
| 4:15-4:40 | Orbyte fit (connector), reuse across 3 tenants, metrics (accuracy, time per receipt), SDG 8/9, business model | Orbyte fit, benefit, clarity |
| 4:40-5:00 | Hardest risk (WhatsApp API access) and fallback; roadmap | Feasibility |

Rules for the demo: use real running software, not mockups; label simulated parts; keep audio clear; have a pre-recorded backup of the live segment.

---

## 16. Proposal text skeleton (problem -> approach -> expected outcome)

**Problem (2-3 sentences).** Malaysian micro and small businesses collect payments through WhatsApp screenshots. Owners manually match each receipt to an invoice, key it into a spreadsheet and chase late payers by hand, so payments are mismatched, reminders are forgotten and cash flow suffers.

**Approach (5 bullets, mirror the brief).**
1. Trigger: customer sends receipt on WhatsApp.
2. Connected data: open invoices, customer and role data from the Orbyte hub.
3. Decision logic: AI reads the receipt; transparent rules score the match and classify exceptions.
4. Human approval: the right role approves with one tap in WhatsApp or dashboard; limits by role.
5. Visible outcome: payment recorded, customer notified, dashboard and tamper-evident audit log updated; overdue invoices chased with approved reminders.

**Expected outcome (measurable).** Cut per-receipt handling from ~3 minutes to ~20 seconds; reduce owner reconciliation time from ~6 hrs/week to ~1 hr/week (assumption, to be validated); >90% auto-match accuracy on our labelled synthetic test set (report actual); 100% of recorded payments human-approved and logged. Supports SDG 8.2 and 8.3, plus SDG 9.

**Orbyte fit + reuse (3 lines).** Consumes hub data via a connector, writes payment events and audit logs back, works across any credit-invoicing SME through tenant configuration.

**Hardest risk + fallback (2 lines).** WhatsApp Business API approval; fallback is a built-in channel simulator with the same webhook contract.

**Business model (optional bonus).** Freemium (e.g. first 30 receipts/month free), then per-tenant subscription tiered by receipt volume; plus partner revenue share with DuitNow QR providers and e-invoicing vendors through Orbyte.

**Growth path (optional bonus).** Phase 1: reconciliation and chasing for Malaysian SMEs. Phase 2: bank statement (CSV/open banking) matching, e-invoice readiness checks, cash-flow forecast. Phase 3: other ASEAN markets with local receipt formats and languages (Singapore PayNow, Indonesia QRIS, Thailand PromptPay).

---

## 17. Pitch deck outline (10 slides, concise)

1. Title + one-line promise ("Orbit: stop chasing receipts on WhatsApp")
2. The problem (specific, with a day-in-the-life)
3. Who we serve (Malaysian micro/small businesses on WhatsApp)
4. Solution: the 5-step journey diagram
5. Live demo / screenshots (core journey)
6. People stay in control: roles, approval, audit log, PDPA
7. Accuracy and ease of learning: test results + time to first approval
8. Orbyte fit and reuse: connector diagram, 3 tenants
9. Business benefit, SDGs, business model, growth path
10. Risks and roadmap + team + GitHub link

---

## 18. Submission checklist

- [ ] Complete and functional repository codebase (public or judge-accessible; matches demo)
- [ ] Proof of Replit utilization (screenshots/deployment URL)
- [ ] Proof of RunPod utilization (only if truly used)
- [ ] Completed submission template (follow the GitHub template and length limits)
- [ ] Completed tech tools declaration (list models, APIs, libraries, AI coding assistants including Claude Code)
- [ ] Pitch deck slides
- [ ] YouTube link for product demo (Unlisted, max 5 min)
- [ ] Fully populated README summary
- [ ] Apache License 2.0 file in repo root
- [ ] Synthetic data only; no secrets committed (use Replit Secrets / `.env`, rotate any leaked key)
- [ ] Re-read the Domain 2 brief once more before hitting submit

---

## 19. Roadmap (present as future work, do not build now)

Bank statement CSV matching to confirm receipts independently; e-invoice readiness checks (preparatory only); cash-flow forecast from expected payments; payment promise tracking ("I'll pay Friday"); partner integrations (DuitNow QR, accounting software); voice-note understanding for BM/Manglish; multi-language reminders; customer self-service payment status link.

---

## 20. Quality bar (mirrored in CLAUDE.md)

- Stack: Python 3.11 + FastAPI + SQLAlchemy 2.0 + SQLite (backend/), React + Vite + Tailwind (frontend/).
- Product name is "Orbit". It is a module for the Orbyte hub (Orbyte is the host platform, not us).
- Runs on Replit. Licence: Apache 2.0. Synthetic data only, never real personal data.
- Keep code simple and boring. The demo must work every time. No over-engineering.
- Money is always integer sen. Never floats.
- Every table has tenant_id; every query is scoped by tenant.
- Every state change goes through a service function that also writes the audit log, in the same transaction.
- AI is only used to read receipts. Matching, approvals and scheduling are deterministic rules.
- Label anything simulated (WhatsApp channel, Orbyte API, login) in UI and API responses.
- Tests only for matching/classification, RBAC and the audit hash chain.
- Only add a dependency to requirements.txt when a step actually needs it.
- Work one step at a time. After each step, state exactly how to check it works.
- Keep the README honest: report real accuracy numbers, including failures.

---

## 21. Decision log

| # | Decision | Reason |
|---|---|---|
| 1 | Product renamed from "PayChase" to **Orbit** | Team choice. Use the tagline "Orbit, payment reconciliation for the Orbyte hub" so judges don't confuse Orbit with Orbyte. |
| 2 | SQLite, not JSONL files | Approvals change 5 records at once and need a transaction; webhook, dashboard and scheduler write concurrently. SQLite is still a single file. JSONL kept only as an audit log export format. |
| 3 | Money stored as integer sen | Avoids float rounding errors in a payments product. |
| 4 | Phone numbers: keyed HMAC + encrypted copy (not plain hash) | We need the real number to send WhatsApp replies; plain hashes of phone numbers are brute-forceable. |
| 5 | `wa_message_id` unique; webhook returns 200 then processes in background | Meta retries deliveries and expects a fast response. |
| 6 | Tests limited to matching/classification, RBAC, audit chain | MVP speed; these are the areas where a silent bug is costly and where tests double as evidence for judges. |
| 7 | Extraction cached by image SHA-256 | Demo never depends on a live LLM call. |
| 8 | FastAPI serves the built frontend in deployment | One public URL for judges. |
| 9 | Python 3.12 instead of 3.11 | 3.11 is not installed on the dev machine (3.12/3.13/3.14 are). 3.12 is the closest version with mature wheels for FastAPI, SQLAlchemy and Pydantic; 3.14 is too new to trust for demo reliability. |
| 10 | SQLAlchemy pinned to the 2.0 line (`>=2.0.36,<2.1`) | An unpinned install resolved to 2.1, a different major line from the one this spec was written against. Pinning keeps the ORM behaviour matching Section 8. |
| 11 | No `temperature` on the extraction call | Section 7.1 asks for temperature 0, but current Claude models reject sampling parameters with a 400. Determinism comes from an API-enforced JSON response schema plus a literal prompt, which is stronger than temperature 0 was. |
| 12 | Hand-rolled Tailwind components instead of shadcn/ui, and no Recharts | MVP, and the repo stays small. shadcn copies dozens of component files in; the dashboard needs about six small ones. KPI bars are plain CSS. |
| 13 | No APScheduler. Chasing runs from a "Run now" button | One less dependency and a deterministic demo. A real deployment points a daily cron at the same function. |
| 14 | Official `anthropic` SDK rather than raw HTTP | Anthropic's own guidance for a Python project. It is a single dependency and is imported lazily, so the default mock path does not need it. |
| 15 | 11 tables, not 12 | Section 8 defines 11 tables. The "12" in section 14 step 1 was a miscount; no table is missing. |
| 16 | Frontend is Next.js, not React + Vite | Asked for by the team. One route per screen instead of in-page state, so a judge can link straight to `/audit`. The AI, matching, classification, audit and API all stay in Python. |
| 17 | Next.js uses `output: 'export'` | The dashboard is entirely client-side against the Python API, so a static export keeps decision 8 intact: FastAPI serves it and there is one URL and no Node process in production. |
| 18 | Tailwind 4.3, not 4.0 | 4.0.0's build plugin crashes on Node 26 ("Cannot convert undefined or null to object"). 4.3.3 builds cleanly. |
| 19 | A duplicate is also detected against a still-pending proposal, not only a recorded payment | Section 7.3 only mentions payments already recorded, which would let the same receipt sit in the inbox twice and be approved twice. The explanation wording distinguishes "already recorded" from "an earlier copy is still waiting". |
| 20 | The Orbyte connector is on the live decision path, not just present in the repo | It was written but nothing called it, so section 6.3 principle 4 ("all hub data goes through `OrbyteConnector`") was not actually true. Invoice and customer master data for every match now comes through the connector, and each approval writes a payment and an activity event back through it, audited as `HUB_SYNCED`. `GET /api/orbyte/status` makes the seam inspectable. The phone HMAC stays on Orbit's side: the hub has no reason to hold it. |
