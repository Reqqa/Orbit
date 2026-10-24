# Orbit build steps (zero to finished product)

Derived from `docs/SPEC.md`. One step at a time, in order. Do not start a step until the
previous one's **Done when** passes. Tick the box, commit, move on.

Legend: **Do** = the work, **Done when** = the check that proves it. Spec sections in brackets.

---

## Phase A — Groundwork (no app code yet)

- [x] **1. Fix `.gitignore`.** Remove the line that ignores `.gitignore` itself; keep `.env`,
      `*.db`, `__pycache__/`, `.pytest_cache/`, `node_modules/`; add `.venv/` and
      `backend/seed/receipts/`. (The build output is `frontend/out/` plus `frontend/.next/`,
      not `frontend/dist/` — the frontend is Next.js, decision log 16.)
      *Done when:* `git check-ignore -v .env .venv backend/seed/receipts/x.png` lists all three and
      `git status` still tracks `.gitignore`.
- [x] **2. Write `CLAUDE.md`** at the repo root: the standing rules from Spec section 20.
      *Done when:* it states name = Orbit, integer sen, tenant_id everywhere, audit in the same
      transaction, AI only reads receipts, label anything simulated, tests limited to
      matching/RBAC/audit. [20]
- [x] **3. Fix `.env.example`.** `DATABASE_URL=sqlite:///./orbit.db` (it still says paychase), plus
      `SESSION_SECRET`, `PHONE_HMAC_KEY`, `PHONE_ENC_KEY`, `LLM_PROVIDER=mock`,
      `ANTHROPIC_API_KEY`, `DEMO_MODE=true`, `TZ=Asia/Kuala_Lumpur`.
      *Done when:* every key the code will read is listed with a safe placeholder and no real secret
      is committed. [decision log 1, 18]
- [x] **4. Create the folder skeleton** exactly as Spec 14.1 (backend/app/{auth,connectors,webhooks,
      services,templates}, backend/tests, backend/seed, frontend, scripts, docs/proof).
      *Done when:* the tree matches 14.1 and every Python package has `__init__.py`.
- [x] **5. `backend/requirements.txt`, minimum only:** fastapi, uvicorn[standard], sqlalchemy,
      pydantic, pydantic-settings, python-multipart.
      *Done when:* `pip install -r requirements.txt` succeeds in a fresh venv. [20: add a dependency
      only when a step needs it]
- [x] **6. `app/main.py` with `GET /api/health`** returning status, name "Orbit", demo mode and a
      `simulated` block.
      *Done when:* `uvicorn app.main:app --reload` serves `/api/health` 200 and `/docs` renders. [14.1]
- [x] **7. `app/config.py`** — pydantic-settings reading `.env`, typed, no secrets in code.
      *Done when:* changing `DEMO_MODE` in `.env` changes the `/api/health` response.

## Phase B — Database

- [x] **8. `app/db.py`** — engine, `SessionLocal`, `Base`, a FastAPI session dependency, SQLite
      `check_same_thread=False` and foreign keys ON.
      *Done when:* a throwaway endpoint opens and closes a session without error.
- [x] **9. `models.py` part 1, hub tables:** `tenants`, `users`, `customers`, `invoices`. Money as
      `*_sen` integers, `tenant_id` on all of them, unique `(tenant_id, invoice_no)`.
      *Done when:* the tables create and the unique constraint rejects a duplicate invoice number. [8]
- [x] **10. `models.py` part 2, ingestion tables:** `whatsapp_messages` (unique `wa_message_id`,
      `simulated` flag), `extractions`, `match_proposals`.
      *Done when:* inserting the same `wa_message_id` twice raises IntegrityError. [8]
- [x] **11. `models.py` part 3, outcome tables:** `payments` (unique `proposal_id`),
      `payment_allocations`, `reminders`, `audit_log` (unique `hash_self`, no update or delete path).
      *Done when:* all 11 tables are defined and every money column is an integer. (Section 8
      defines 11; the "12" in section 14 step 1 was a miscount — decision log 15.) [8]
- [x] **12. Create tables on startup** with `Base.metadata.create_all`.
      *Done when:* `sqlite3 orbit.db ".tables"` lists all 11 tables. (Section 8 defines 11;
      the "12" in section 14 step 1 was a miscount — decision log 15.)

## Phase C — Trust primitives

- [x] **13. `services/crypto.py`** — `phone_hmac(n)` (keyed, stable) plus `encrypt_phone` and
      `decrypt_phone` (Fernet, key from env). Add `cryptography`.
      *Done when:* a number round-trips through encrypt/decrypt and the HMAC is identical across two
      process runs. [14 step 2, decision log 4]
- [x] **14. Money helpers.** `to_sen("850.00") -> 85000`, `fmt_sen(85000) -> "RM 850.00"`.
      *Done when:* no float appears anywhere in money handling.
- [x] **15. `services/audit.py`, write side.** `write_audit(session, ...)` sets
      `hash_self = sha256(hash_prev + canonical row json)` and runs inside the caller's transaction,
      never its own commit.
      *Done when:* two consecutive writes chain, row 2's `hash_prev` equals row 1's `hash_self`. [8, 20]
- [x] **16. `services/audit.py`, verify side.** `verify_chain(tenant_id)` returns ok, rows checked and
      the first bad row id.
      *Done when:* it returns ok on seeded data. [14 step 3]
- [x] **17. `tests/test_audit_chain.py`** — write three rows and verify ok; mutate one row directly in
      SQL; verify fails and names that row. Add pytest.
      *Done when:* `pytest tests/test_audit_chain.py` passes. [14.3]

## Phase D — Seed data

- [x] **18. `seed/generate_data.py` part 1, tenants and users.** Three tenants (hardware trader, bakery
      supplier, tuition centre), each with an Owner, a Finance user (limit RM 2,000, stored as 200000
      sen) and a Sales user.
      *Done when:* the script prints 3 tenants and 9 users. [8.1, 4]
- [x] **19. Seed part 2, customers.** 25 per tenant, Malay, Chinese and Indian names, some with aliases
      ("Ah Seng" vs "Tan Ah Seng Enterprise"), language BM/EN/ZH, phone HMAC plus encrypted copy, and
      a couple flagged disputed.
      *Done when:* 75 customers exist and at least five have aliases. [8.1]
- [x] **20. Seed part 3, invoices.** About 80 across the tenants, mixed OPEN/PARTIAL/PAID, due dates
      overdue by 1, 7 and 14+ days plus some in the future.
      *Done when:* the script prints a status and overdue-bucket breakdown. [8.1]
- [x] **21. Make the seed re-runnable.** A `--reset` flag, and a fixed random seed so demos repeat.
      *Done when:* running it twice gives identical counts and the same first customer name.

## Phase E — Orbyte connector, login, RBAC

- [x] **22. `connectors/orbyte_base.py`** — the `OrbyteConnector` interface for the seven assumed
      endpoints in Spec 13 (tenants, users, customers, invoices, payments, activity log, notifications).
      *Done when:* the abstract class exists with typed signatures and a docstring saying these
      endpoints are our own documented assumption. [13]
- [x] **23. `connectors/orbyte_mock.py`** — `MockOrbyteConnector` served from the local DB, every
      response carrying `simulated: true`.
      *Done when:* fetching open invoices for tenant 1 returns seeded rows marked simulated. [6.3.4]
- [x] **24. Simulated login and role switcher.** `POST /api/session` sets a signed cookie with tenant,
      user and role; `GET /api/session` returns the current role and tenant name, labelled
      `simulated_login: true`.
      *Done when:* switching to Sales and re-reading the session shows the new role. [9.9, 6.2]
- [x] **25. `auth/rbac.py`** — `require(permission)` and `can_approve(role, amount_sen, confidence)`.
      Owner everything, Finance up to their limit, Sales read-only and scoped to their own customers.
      *Done when:* the helpers return the right answers for every row of the Spec 4 table.
- [x] **26. Log every denial.** A 403 writes an audit row with action `APPROVAL_DENIED` before raising.
      *Done when:* a Sales approve attempt returns 403 and the attempt is in the audit log. [14 step 5]
- [x] **27. `tests/test_rbac.py`** — Sales cannot approve, Finance over the limit is refused, both
      denials are logged.
      *Done when:* `pytest tests/test_rbac.py` passes. [14.3]
- [x] **28. Tenant scoping dependency.** One helper that every query path uses, so no endpoint can read
      across tenants.
      *Done when:* asking for tenant 2's invoice while logged into tenant 1 returns 404, not data. [6.3.5]

## Phase F — WhatsApp ingestion

- [x] **29. Meta-shaped payload models** for text and image messages (entry, changes, value, messages)
      as Pydantic schemas.
      *Done when:* a saved sample Meta payload parses without error. [5.1.2]
- [x] **30. `GET /webhooks/whatsapp`** verification handshake (mode, verify token, challenge).
      *Done when:* the right token echoes the challenge and a wrong one gets 403. [14.2]
- [x] **31. `POST /webhooks/whatsapp`** — verify `X-Hub-Signature-256`, return 200 immediately, queue a
      background task.
      *Done when:* a bad signature is rejected and a good one returns 200 well under a second.
      [decision log 5]
- [x] **32. Store the message.** Insert into `whatsapp_messages` with a media reference only, identify
      the tenant by receiving number and the customer by `phone_hmac`; an unknown sender is allowed and
      left unlinked.
      *Done when:* a seeded customer's number resolves to that customer. [5.1.2]
- [x] **33. Idempotency.** A duplicate `wa_message_id` is ignored, not an error.
      *Done when:* posting the same payload twice leaves one row and both calls return 200. [14 step 6]

## Phase G — Synthetic receipts

- [x] **34. `seed/generate_receipts.py`** — Pillow, generic layout, fictional bank names, no trademarks:
      header, amount, date and time, payer, payee, reference, transaction id.
      *Done when:* ten PNGs open and read as plausible generic receipts. [8.1, 14 step 7]
- [x] **35. `seed/ground_truth.csv`** — one labelled row per image: filename, every true field and the
      expected classification.
      *Done when:* ten rows, no blanks, amounts as plain decimals. [8.1]
- [x] **36. Three tricky variants now** (cropped reference, blurry, non-receipt photo) so the edge-case
      code has inputs from the start. The full 50 comes at step 77.
      *Done when:* the three exist and are labelled in `ground_truth.csv`.

## Phase H — Extraction (the only AI)

- [x] **37. `services/extraction.py` interface.** `Extractor.extract(image_bytes) -> ExtractionResult`.
      *Done when:* the abstract class exists and nothing else imports a model SDK directly. [6.2]
- [x] **38. Strict output schema.** A Pydantic model for the Spec 7.1 JSON contract including
      `field_confidence` and `is_payment_receipt`; reject a missing or non-positive amount; convert to
      integer sen immediately after validation.
      *Done when:* a malformed payload raises a clear validation error. [7.1]
- [x] **39. `MockExtractor`.** Looks up `ground_truth.csv` by image SHA-256 and returns the labelled
      answer, tagged `model_name="mock"`.
      *Done when:* one demo image returns valid JSON with no network call. [14 step 8]
- [x] **40. SHA-256 extraction cache.** Store the raw JSON in `extractions` keyed by `image_sha256`;
      a repeat extraction of the same image is a cache hit.
      *Done when:* the second call makes no provider call and logs a hit. [decision log 7]
- [x] **41. `ClaudeExtractor`.** Vision, strict JSON, one retry on invalid JSON, then fall back to
      `LOW_CONFIDENCE` for human review. Chosen by `LLM_PROVIDER`. Built with **no `temperature`
      parameter** — current Claude models reject sampling parameters, so determinism comes from an
      API-enforced JSON response schema (decision log 11).
      *Done when:* with a key set one real image returns valid JSON, and with the key removed the app
      still runs on the mock. [7.1, 12]
- [x] **42. Wire extraction into the webhook background task.** Store the extraction row against the
      message; `is_payment_receipt=false` short-circuits to a polite reply, logged, no record.
      *Done when:* sending the non-receipt photo takes the friendly reply path. [5.1.3, 7.3]

## Phase I — Matching and classification (deterministic)

- [x] **43. Normalisation helpers.** Invoice number and reference normalisation (strip spaces, dashes,
      case) and name normalisation for fuzzy compare. Add `rapidfuzz`.
      *Done when:* "inv 1042", "INV-1042" and "inv1042" all normalise equal.
- [x] **44. `services/matching.py`, the pure scorecard.** The six Spec 7.2 signals with per-tenant
      weights from `settings_json`, returning a ranked candidate list with a per-signal breakdown and
      no DB access inside the scoring function.
      *Done when:* calling it with plain dicts returns a 0-100 score plus the breakdown. [7.2]
- [x] **45. `tests/test_matching.py`** — exact, partial, overpayment, multi-invoice.
      *Done when:* `pytest tests/test_matching.py` passes. [14 step 9]
- [x] **46. `services/classify.py`, the data-driven cases:** EXACT_MATCH, PARTIAL_PAYMENT, OVERPAYMENT,
      MULTI_INVOICE, UNMATCHED, LOW_CONFIDENCE, using the Spec 7.3 thresholds.
      *Done when:* each case is reachable with a hand-built input. [7.3]
- [x] **47. Duplicate detection.** Same `transaction_id`, or the same amount, payer and date within 24
      hours of a recorded payment, gives DUPLICATE and blocks auto-recording.
      *Done when:* replaying an already-recorded receipt classifies DUPLICATE. [7.3]
- [x] **48. Multi-invoice allocation proposal.** An amount equal to the sum of two or more open invoices
      proposes an oldest-first allocation for the owner to confirm.
      *Done when:* a two-invoice receipt produces a two-line allocation that sums to the amount. [7.3]
- [x] **49. Explanation builder.** Template text only, no LLM: which signals matched, which are missing,
      in plain language ("Reference number not found, please confirm").
      *Done when:* an explanation lists matched and missing signals and never contains model prose.
      [5.1.6, 6.3.3]
- [x] **50. `tests/test_classify.py`** — all eight cases including NOT_A_RECEIPT.
      *Done when:* `pytest tests/test_classify.py` passes. [14 step 10]

## Phase J — Proposals, approval, ledger

- [x] **51. Create the proposal.** Persist a `match_proposals` row with classification, candidates,
      confidence, explanation and status PENDING.
      *Done when:* a simulated receipt produces exactly one pending proposal. [8]
- [x] **52. Approval routing.** `requested_approver_role` is Finance when the amount is within their
      limit and confidence is at least 90, otherwise Owner; every exception type goes to Owner.
      *Done when:* RM 3,000 routes to Owner and RM 500 routes to Finance. [14 step 11, 4]
- [x] **53. `GET /api/approvals?status=pending`** — tenant-scoped and role-filtered, including the image
      reference, extracted fields, candidates, confidence and explanation.
      *Done when:* Owner sees the item and Sales sees an empty list. [14.2]
- [x] **54. `services/ledger.py`, the atomic outcome.** One transaction: insert the payment, insert the
      allocations, update invoice `outstanding_sen` and status, write the audit rows.
      *Done when:* a forced error mid-way leaves the invoice untouched, proving rollback. [5.1.8, 6.3.6]
- [x] **55. `POST /api/approvals/{id}/decision`** — decision, note and edits; RBAC and limit enforced
      server-side; edits stored alongside the original extraction.
      *Done when:* approving moves an invoice OPEN to PAID with a full audit trail. [14 step 12]
- [x] **56. Reject path.** Proposal REJECTED with a reason, no ledger change, customer asked to clarify,
      everything logged.
      *Done when:* rejecting leaves the invoice OPEN and the reason is in the audit log. [5.1.8]
- [x] **57. `templates/` and `services/notify.py`.** A `Sender` interface with `SimulatorSender` first,
      BM/EN/ZH templates with variables, no free-form wording.
      *Done when:* approval emits "Thanks Ahmad, RM 850.00 received for INV-1042" in the customer's
      language. [7.4, 9]
- [x] **58. End-to-end smoke by API only.** Simulator send, extraction, proposal, approve, payment,
      audit.
      *Done when:* one shell script runs the whole journey on a fresh DB and prints the final invoice
      status.

## Phase K — Remaining read APIs

- [x] **59. `GET /api/invoices`, `/api/customers`, `/api/payments`** — filters, tenant-scoped, Sales
      limited to their own customers.
      *Done when:* the same request as Sales returns a strict subset of the Owner's. [14.2, 4]
- [x] **60. `GET /api/dashboard/summary`** — needs-approval count, overdue total, received this week,
      and the KPI strip numbers.
      *Done when:* an approval changes the numbers on the next call. [9]
- [x] **61. Invoice timeline endpoint** — created, reminder sent, receipt received, approved, paid.
      *Done when:* the demo invoice returns its events in chronological order. [9.3]
- [x] **62. `GET /api/audit`, `/api/audit/verify`, `/api/audit/export.jsonl`.**
      *Done when:* the export downloads as JSONL and an independent re-hash of that file verifies the
      chain. [8]
- [x] **63. `POST /api/simulator/send`** — demo mode only, builds a real Meta-shaped payload and posts it
      through the same webhook, 404 when `DEMO_MODE=false`.
      *Done when:* the simulator path and a genuine webhook call produce identical DB state. [12]
- [x] **64. `POST /v1/receipts/analyze`** — the reusable building block: image in, fields and candidates
      out, no writes.
      *Done when:* it is documented on `/docs` and changes nothing in the DB. [13]

## Phase L — Frontend

- [x] **65. Scaffold `frontend/`** — React, Tailwind, dev proxy to the backend. Built as
      **Next.js (App Router) with a static export** and hand-written Tailwind components, not
      Vite and not shadcn/ui (decision log 12 and 16).
      *Done when:* `npm run dev` shows a styled placeholder page.
- [x] **66. API client and role switcher.** Typed fetch wrapper, session handling, a header dropdown for
      Owner/Finance/Sales and a visible "Simulated login" badge.
      *Done when:* the page shows the current role and tenant name from the API. [14 step 13]
- [x] **67. App shell.** Navigation for the eight screens, loading and empty states with guidance.
      *Done when:* every route renders a titled page and there are no dead links. [9]
- [x] **68. Simulator screen.** Phone-style chat, pick a customer, upload a receipt, watch the bot reply;
      a second panel shows the owner's phone with buttons; "Simulated channel" always visible.
      *Done when:* uploading a receipt creates a proposal. [14 step 14, 9.8]
- [x] **69. Approval inbox, the card.** Receipt image on the left, extracted fields on the right,
      suggested invoice, confidence bar, "Why we think so", missing info in amber.
      *Done when:* a pending proposal renders with all of its evidence visible. [9.2]
- [x] **70. Approval inbox, the actions.** Approve, Edit and Reject wired to the decision endpoint; Sales
      sees the permission error rather than a hidden button.
      *Done when:* you can approve end to end from the UI. [14 step 15]
- [x] **71. Today dashboard.** The three cards and the "Review approvals" primary button.
      *Done when:* an approval visibly changes the KPIs. [9.1]
- [x] **72. Ledger and invoice timeline screens.**
      *Done when:* clicking the demo invoice shows the approval you just made in its timeline. [9.3]
- [x] **73. Audit screen.** Searchable table, AI versus human colour-coded, "Verify integrity" and
      "Export .jsonl".
      *Done when:* verify shows ok, and tampering with a row in SQL makes it fail on screen. [9.6, 15]
- [x] **74. Customers screen.** Balance, last payment, reminder history.
      *Done when:* the demo customer's balance matches the ledger. [9.5]
- [x] **75. Settings screen, Owner only.** Approval limits, thresholds, chase ladder, quiet hours and
      templates, reading and writing `tenants.settings_json`.
      *Done when:* lowering the Finance limit immediately changes approval routing. [9.7]
- [x] **76. One URL.** Build the export and have FastAPI serve `frontend/out`.
      *Done when:* a single port serves both the dashboard and `/docs`. [decision log 8]

## Phase M — Demo-ready checkpoint (the preliminary-round bar)

- [x] **77. Grow the receipt set to 50**, covering every tricky case in Spec 8.1 (partial, overpayment,
      duplicate, two-invoice, wrong amount, BM text, blurry, cropped, non-receipt), all labelled.
      *Done when:* `ground_truth.csv` has 50 rows and each classification appears at least twice.
- [x] **78. Run ten receipts end to end** through the UI and fix what breaks.
      *Done when:* ten out of ten reach the correct final state with no manual DB fixes. [14 checkpoint]
- [ ] **79. Deploy to Replit** (`.replit`, build step, Secrets, Deployment) and save screenshots to
      `docs/proof/replit-*.png`. Step-by-step, with the storage finding, in
      [`connect-replit.md`](connect-replit.md).
      *Done when:* a public URL loads the dashboard and `/api/health`. [18]
- [ ] **80. Record the backup demo video** of the live segment before anything else changes.
      *Done when:* a watchable clip of the core journey exists on disk. [14 checkpoint, 15]

## Phase N — Stretch, strictly in this order

- [ ] **81. Real WhatsApp Cloud API**, time-boxed to three or four hours: test number, `CloudApiSender`,
      templates, signature. If blocked, stop and keep the simulator. **Partly done:** the code path
      is written and verified as far as it can be without a Meta account — see the status table and
      [`connect-whatsapp.md`](connect-whatsapp.md).
      *Done when:* either a real message round-trips, or the time box expired and the decision is
      written into the decision log. [14 step 17, 12]
- [x] **82. Chasing, the rules.** `services/chasing.py`: the -3, +1, +7, +14 ladder plus the guards
      (pending approval, disputed, promised-pay date, three-day cooloff, quiet hours).
      *Done when:* a dry run over seeded invoices lists the right customers per rung and names the skip
      reason for every exclusion. [7.4]
- [x] **83. Chasing, scheduler and batch.** Built without a background scheduler: the "Run now"
      button drives the ladder (`services/chasing.py` says so at the top), drafts are stored as
      `reminders` rows, with `GET /api/chasing/batch/tomorrow` and
      `POST /api/chasing/batch/{batch_date}/approve`.
      *Done when:* approving a batch sends through the simulator and tracks statuses. [14 step 18]
- [x] **84. Chasing screen.** Batch preview, per-customer skip toggle, tone, "Approve batch".
      *Done when:* the demo batch can be previewed, trimmed and approved in the UI. [9.4]
- [x] **85. `scripts/eval_accuracy.py`** — run all 50 against `ground_truth.csv` and report per-field
      extraction accuracy, auto-match rate and a classification confusion matrix.
      *Done when:* it prints a table you are willing to publish, failures included. [14 step 19, 11]

## Phase O — Submission pack

- [x] **86. `README.md`** — problem, approach, outcome, run steps, the real accuracy table, PDPA
      summary, risks, and what is simulated.
      *Done when:* someone can clone and run it from the README alone and the numbers match step 85. [20]
- [x] **87. `TECH_TOOLS_DECLARATION.md`** — every model, API, library and AI coding assistant, Claude
      Code included, and where each was used. [18]
- [x] **88. `docs/demo-script.md`** — the Spec 15 timed script, then the ten-slide deck from Spec 17.
      *Done when:* a dry run lands under 5:00. [15, 17]
- [ ] **89. Record and upload the final demo video** (YouTube, Unlisted, five minutes maximum), with the
      backup clip ready. [15, 18]
- [ ] **90. Walk the Spec 18 checklist** line by line, confirm synthetic data only and no committed
      secrets, re-read the Domain 2 brief, submit. [18]

---

## Notes carried over from the repo scan

- The repo currently holds only `LICENSE`, a one-line `README.md`, `.gitignore`, `.env.example` and
  `docs/SPEC.md`. Steps 1 to 3 clean up what is there, including `.gitignore` ignoring itself and
  `.env.example` still naming `paychase.db`.
- `CLAUDE.md` does not exist yet even though the spec refers to it. That is step 2.
- Steps 1 to 80 are the committed scope. Steps 81 to 85 are stretch, dropped without regret if the
  deadline closes in. Steps 86 to 90 are not optional.

---

## Status, 2026-10-24

Steps 1 to 78, plus 82 to 88, are done and verified on this machine. What that means
concretely:

- `cd backend && python -m pytest -q` → **40 passed**.
- The full journey runs end to end: simulated receipt → extraction → scorecard →
  classification → routed proposal → approval in one transaction → invoice `OPEN` to
  `PAID` → templated confirmation → audit row. Checked over HTTP, not just in Python.
- Sales approving gets **403** and the attempt is in the audit log. Lowering the Finance
  limit on the Settings screen moves the next payment from Finance to Owner immediately.
- Audit chain verifies per tenant; editing a row breaks it and names the row.
- 10 of 10 receipts classified as labelled; 47 of 50 over the whole set
  (`docs/accuracy.md`).
- `cd frontend && npm run build` exports all 9 routes; FastAPI serves them, so the
  dashboard and `/docs` share one URL.

## Beyond the plan

Two pieces of work landed after the 90 steps were written. They are not renumbered; they
are recorded here.

| What | Where | State |
|---|---|---|
| The Orbyte connector moved onto the live decision path | `services/proposals.py` scores every receipt against invoices and customers fetched through `OrbyteConnector`; `services/approval.py` calls `record_payment` (idempotency key `orbit-proposal-<id>`) and `push_activity` on every approval and writes a `HUB_SYNCED` audit row; `GET /api/orbyte/status` and `/api/orbyte/preview` expose it | Done and verified. Still the mock connector, every response tagged `"simulated": true` (decision log 20, [`connect-orbyte.md`](connect-orbyte.md)) |
| A live WhatsApp sender and inbound media download | `services/notify.py` — `get_sender()` returns `CloudApiSender` (Graph `v26.0`, `httpx`) when `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_ID` are both set, the simulator otherwise; `webhooks/whatsapp.py` downloads inbound media from Meta by media id and saves it through `app.media.save_media` | Code done; verified only against an injected fake `http_post`, never against Meta. Feeds step 81 ([`connect-whatsapp.md`](connect-whatsapp.md)) |

---

**The remaining steps need your accounts or your camera, not more code:**

| Step | Why it is still open |
|---|---|
| 79 — Replit deploy | `scripts/replit-start.sh` and `.replit` are committed and the script parses, but every Replit-specific line is unverified and deploying needs your account. The script says so at the top. [`connect-replit.md`](connect-replit.md) has the walkthrough, and two findings that change the plan: no Replit deployment target keeps filesystem data, so the SQLite file does not survive a redeploy (the boot script reseeds, so it self-heals, but judge clicks are lost), and the only target suited to one SQLite file, Reserved VM, is paid from about USD 15/month. The recommendation there is to record the video against the free development URL and publish only if a persistent link is required. |
| 80, 89 — demo videos | Needs screen recording and a YouTube upload. `docs/demo-script.md` is the shot-by-shot script. |
| 81 — real WhatsApp Cloud API | **Partly done.** The live path is implemented: the sender switches to `CloudApiSender` on configuration and inbound media is downloaded from Meta by media id, both verified as far as they can be here — with an injected fake HTTP post, no Meta account involved. What is left needs accounts, not code: a Meta Business account and test number, a public HTTPS callback URL, and **approved template messages** for the three business-initiated chase reminders, which `CloudApiSender` cannot send as free-form text outside Meta's 24-hour window. Steps and citations: [`connect-whatsapp.md`](connect-whatsapp.md); the gap is in the `docs/SPEC.md` section 12 risk table. The simulator remains the committed fallback and is unaffected. |
| 90 — submission | The checklist in `docs/SPEC.md` section 18, to walk before you submit. |
