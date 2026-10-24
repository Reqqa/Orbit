# Orbit architecture

Orbit is a WhatsApp payment-reconciliation module for the Orbyte business hub: a customer
sends a transfer receipt over WhatsApp, Orbit reads it, scores it against the open
invoices, explains what it thinks, and waits for a person to approve before anything is
recorded. The shape is one sentence long: **a Python API does all the thinking, and it
also serves a static Next.js dashboard out of `frontend/out`, so there is one URL and no
Node process in production.** Everything deterministic lives in Python; AI is used in
exactly one function, reading an image into JSON.

Counts, for orientation: 44 Python files under `backend/` (including `__init__.py`), 22
JS/JSX files under `frontend/app`, `frontend/components` and `frontend/lib`, 11 database
tables, 25 documented API paths on `/docs`, 40 tests in 4 files. Companion documents:
[SPEC.md](SPEC.md) (spec and decision log), [accuracy.md](accuracy.md) (generated — do
not hand-edit), [STEPS.md](STEPS.md), [demo-script.md](demo-script.md), and the research
notes [connect-whatsapp.md](connect-whatsapp.md), [connect-replit.md](connect-replit.md),
[connect-orbyte.md](connect-orbyte.md).

---

## 1. The request journey

This is the real call stack for one receipt, in order. Every name below is a function you
can open.

1. **A message arrives.** Either `POST /webhooks/whatsapp` →
   `app/webhooks/whatsapp.py::receive`, which first calls `_check_signature` (verifies
   Meta's `x-hub-signature-256`, and is a no-op when no `WHATSAPP_APP_SECRET` is set), or
   the demo path `POST /api/simulator/send` → `app/api/simulator.py::simulator_send`,
   which saves the uploaded image with `app.media.save_media` and then calls
   `app/webhooks/whatsapp.py::build_payload` to construct a genuine Meta-shaped payload.
   Both paths converge on the same function, which is the point.
2. **`ingest_payload`** (same file) walks `entry[].changes[].value.messages[]`, resolves
   the tenant from the business number via `_tenant_for` and the sender with
   `_customer_for` on a keyed phone HMAC, and inserts one `WhatsappMessage` each.
   `wa_message_id` is `unique`, so a Meta retry is skipped and logged. It writes a
   `MESSAGE_RECEIVED` audit row and **does not commit** — the caller owns the transaction.
3. **Processing happens out of band** for the webhook: `receive` returns 200 immediately
   and queues `_process(message_id)` as a FastAPI `BackgroundTasks` job (decision log 5).
   The simulator calls `process_message` inline instead, so the demo shows the result at
   once. Same function either way.
4. **`_process`** loads the image with `app.media.load_media`. If the row references a
   Meta media id with nothing on disk and the live channel is configured, it calls
   `_download_cloud_media` (two-step Graph download, `UNVERIFIED` against a real account),
   rewrites `media_ref` and audits `MEDIA_DOWNLOADED`; a failure audits
   `MEDIA_DOWNLOAD_FAILED` and stops rather than letting an imageless message reach the
   decision path.
5. **`app/services/proposals.py::process_message`** is the pipeline. No image means a
   `MESSAGE_IGNORED` audit row and nothing else.
6. **`extract_for_message`** (`app/services/extraction.py`) hashes the image, returns a
   cached `Extraction` row if that SHA-256 was read before, otherwise calls
   `get_extractor().extract(...)`. A failure becomes `unreadable_receipt(...)`, which is a
   valid `ExtractedFields` with zero confidence — so failure routes to a human instead of
   raising. `process_message` then writes a `RECEIPT_READ` audit row with `actor_type=AI`.
7. **`decide`** is the only database-aware part of the decision. It fetches open invoices
   and customer master data **through `OrbyteConnector`**, never by direct query, then
   calls `matching.score_candidates` (pure), `matching.find_multi_invoice_combination`
   (exact-sum subset search over 2–3 invoices) and `find_duplicate` (same transaction id,
   or same amount from the same customer inside 24 hours, or an earlier unresolved
   proposal for the same transaction id).
8. **`classify_service.classify`** (`app/services/classify.py`) picks one of eight
   classifications by strict precedence, and `build_explanation` writes the headline,
   matched lines, missing lines and next step **from templates only**.
9. **The proposal is written.** `process_message` stores the top five candidates, the
   confidence and the explanation with the allocation plan embedded, then routes it with
   `required_role`: Finance for a strong, non-exception match inside the Finance limit,
   Owner for everything else. Audit row: `PROPOSAL_CREATED`. A `NOT_A_RECEIPT` verdict is
   auto-rejected and the customer gets a templated reply. One `session.commit()`.
10. **A human decides**, later: `POST /api/approvals/{id}/decision` →
    `app/services/approval.py::decide_proposal`. It re-checks tenant, status, permission
    (`has_perm`) and limits (`can_approve`) server-side; every refusal goes through
    `rbac.deny`, which writes the audit row, commits it, and returns the 403.
11. **On approve**, `_approve` calls `ledger.apply_payment` (creates the `Payment`, the
    `PaymentAllocation` rows, moves each invoice's `outstanding_sen` and status, audits
    `PAYMENT_RECORDED` and `INVOICE_UPDATED`), then pushes to the hub
    (`record_payment` with idempotency key `orbit-proposal-<id>`, plus `push_activity`,
    audited as `HUB_SYNCED`), then `notify_customer` renders a template and sends it.
    **One `session.commit()` at the end of all of it** — the payment, the invoices, the
    audit rows and the outbound message land together or not at all.

```
WhatsApp / simulator
        |
   ingest_payload ....... WhatsappMessage  (dedupe on wa_message_id)
        |
   extract_for_message .. Extraction      (cached by image SHA-256)
        |
   decide ............... score_candidates + classify  (pure, no AI)
        |
   process_message ...... MatchProposal   (PENDING, routed by required_role)
        |
   [ human approves ]
        |
   apply_payment ........ Payment + PaymentAllocation + Invoice moved
                          + audit rows + hub sync + customer reply
```

---

## 2. Backend modules

### App root (`backend/app/`)

| File | What it owns |
| --- | --- |
| `main.py` | FastAPI app, router wiring, `/api/health` (states what is simulated), startup `init_db()`, and mounting `frontend/out` last so API routes always win. |
| `config.py` | `Settings` from env/`.env`, cached by `lru_cache`. `whatsapp_live` and `using_placeholder_secrets` are the two derived flags everything else reads. |
| `db.py` | Engine, `SessionLocal`, `Base`, the `get_session` request dependency, `PRAGMA foreign_keys=ON`. No migrations: the schema is created on startup. |
| `models.py` | All 11 tables and the status/role constants. |
| `schemas.py` | Pydantic contracts shared by extraction, matching, classification and the API, plus the weights and thresholds. No ORM, no session. |
| `money.py` | Integer sen only. `to_sen` parses "RM 1,250.50" via `Decimal`; `fmt_sen` formats back. No floats anywhere. |
| `media.py` | Receipt images on disk, named by their own SHA-256 (idempotent storage, and it hands the extraction cache its key for free). `load_media` guards against path escape. |

### Services (`backend/app/services/`)

| File | What it owns |
| --- | --- |
| `extraction.py` | The one AI seam. `Extractor` ABC, `MockExtractor` (ground-truth CSV by SHA-256), `ClaudeExtractor` (vision + API-enforced JSON schema, SDK imported lazily, one retry), `get_extractor`, the cache in `extract_for_message`. |
| `matching.py` | The deterministic scorecard: six weighted signals, `rapidfuzz` name similarity, `hmac.compare_digest` phone check, and the exact-sum multi-invoice search. Pure functions. |
| `classify.py` | The eight verdicts, their precedence, and the templated explanation. Pure functions; duplicate and multi-invoice findings arrive as arguments so the rules stay trivially testable. |
| `proposals.py` | The pipeline (`process_message`), the decision assembly (`decide`), duplicate detection, `required_role` routing, hub→view adapters. |
| `approval.py` | The approval gate. Role and limit checks, allocation resolution (approver's edit wins over the proposal's plan), the one-transaction approve path, the reject path. |
| `ledger.py` | `apply_payment`: payment, allocations, invoice status moves, audit rows. Raises `LedgerError` rather than committing anything partial. |
| `audit.py` | `canonical`, `row_hash`, `write_audit` (never commits), `verify_chain`, `export_jsonl`. |
| `chasing.py` | The overdue ladder (−3, +1, +7, +14 days), the four skip guards, quiet hours, batch drafting and batch sending. No scheduler: `build_batch` is driven by a button (decision log 13). |
| `notify.py` | Outbound messages. `Sender` ABC, `SimulatorSender`, `CloudApiSender` (`UNVERIFIED` against Meta), `get_sender`, `notify_customer`. Owns `GRAPH_API_VERSION = v26.0`, which the webhook imports so send and download cannot drift. |
| `crypto.py` | Phone privacy: `normalise_phone`, keyed `phone_hmac`, Fernet `encrypt_phone`/`decrypt_phone`, `mask_phone`. Rough edge: with no `PHONE_ENC_KEY` the Fernet key is **derived from the HMAC key** so a fresh checkout runs — fine for a demo, not a real key. |

### API (`backend/app/api/`)

| File | What it owns |
| --- | --- |
| `session.py` | `/api/session` (who am I, `simulated_login: true`), `/api/session/users` and the role switcher. The last two are demo-mode only. |
| `approvals.py` | The inbox, one item with all its evidence, and the decision endpoint. Serialisation only; the rules live in `services/approval.py`. |
| `data.py` | Customers, invoices, an invoice timeline, payments, the dashboard summary, settings read/write, and `/api/media/{ref}`. Every query is tenant-scoped and a Sales user is narrowed to `_own_customer_ids`. |
| `audit.py` | List, `verify`, and `export.jsonl`. There is deliberately no endpoint that changes or deletes an audit row. |
| `chasing.py` | Preview the waiting drafts, "run now" to recalculate today's ladder, approve a batch. |
| `orbyte.py` | `/api/orbyte/status` (live connector class, what it reads, the seven assumed endpoints, what never leaves Orbit) and `/api/orbyte/preview` (raw records). Makes the seam visible rather than claimed. |
| `simulator.py` | `/api/simulator/send`, `/api/simulator/thread/{id}`, and `POST /v1/receipts/analyze` — the reusable read-only block another Orbyte module could call: image in, fields and candidates out, nothing recorded. |

### Auth, connectors, webhooks, templates, seed, tests

| File | What it owns |
| --- | --- |
| `auth/session.py` | The simulated login: a stdlib-HMAC-signed cookie naming tenant, user and role. In demo mode no cookie falls back to the first Owner; outside demo mode it is a 401. |
| `auth/rbac.py` | The permission matrix, `can_approve` (Owner anything; Finance only non-exception, within limit, at or above the strong threshold), and `deny`, which audits and commits the refusal before the 403. |
| `connectors/orbyte.py` | `OrbyteConnector` ABC (one method per assumed endpoint), `MockOrbyteConnector` (reads local rows; writes are echoes), `get_connector`. Every returned dict carries `"simulated": true`. |
| `webhooks/whatsapp.py` | The GET handshake, the POST delivery, `ingest_payload`, `_process`, `_download_cloud_media` (`UNVERIFIED`), and `build_payload` for the simulator. |
| `templates/messages.py` | Every word a customer ever receives: 7 templates × 3 languages (EN/BM/ZH), `str.format` placeholders, nothing model-generated. Note: this package has no `__init__.py` and works as an implicit namespace package. |
| `seed/generate_data.py` | The deterministic dataset: 3 tenants, 9 users, 75 customers, 80 invoices, one fixed seed, due dates anchored to today. |
| `seed/generate_receipts.py` | 50 synthetic receipt PNGs drawn with Pillow plus the committed `seed/ground_truth.csv`, keyed by image SHA-256. The images are gitignored and regenerate byte-identical. |
| `tests/conftest.py` | Points `DATABASE_URL` at a temp file **before** importing `app`, because `app.db` builds the engine and `get_settings` caches on first call. Throwaway database per test. |
| `tests/test_matching.py` · `test_classify.py` · `test_rbac.py` · `test_audit_chain.py` | 40 tests over the scorecard, the eight verdicts, approval permissions, and chain tampering. **There are no UI, webhook, or seed tests, by design** — the webhook and simulator paths are exercised by hand. |

---

## 3. The data model

11 tables, all in `app/models.py`.

| Table | For |
| --- | --- |
| `tenants` | One business. `settings_json` holds per-tenant match weights, thresholds and chase config. |
| `users` | Name, role (OWNER/FINANCE/SALES), `approval_limit_sen`. |
| `customers` | Master data: name, aliases, language, assigned sales user, flags such as `disputed`. |
| `invoices` | The ledger. `total_sen`, `outstanding_sen`, status OPEN/PARTIAL/PAID/VOID. Unique `invoice_no` per tenant. |
| `whatsapp_messages` | Every message in and out. `wa_message_id` unique — the idempotency key. `media_ref` is a reference, never bytes. |
| `extractions` | What the model read, as `raw_json`, with the model name and the image SHA-256 that keys the cache. |
| `match_proposals` | One decision waiting for a human: classification, confidence, top candidates, explanation (with the allocation plan), requested approver role, outcome. |
| `payments` | A recorded payment. `proposal_id` is **unique**, which is the idempotency guard: one approved proposal can only ever produce one payment. |
| `payment_allocations` | How much of a payment went against which invoice. |
| `reminders` | A chase draft or a sent chase: rung (−3/+1/+7/+14), template id, rendered body, status. |
| `audit_log` | Append-only, hash-chained, one chain per tenant. |

Three conventions matter more than the schema itself:

1. **Integer sen, everywhere.** Every money column ends in `_sen` and holds an integer;
   `RM 850.00` is `85000`. `app/money.py` is the only place a decimal is parsed, and no
   float appears in the codebase.
2. **`tenant_id` on every business table, and every query scopes by it.** The connector
   takes `tenant_id` as its first argument on every method for the same reason.
3. **Phones are stored twice.** `phone_hmac` is a keyed HMAC-SHA256 (keyed, not a plain
   hash, because the space of Malaysian mobile numbers is brute-forceable) and is the
   indexed lookup value; `phone_enc` is a Fernet ciphertext decrypted only to send a
   reply. Display is always `mask_phone`, and the HMAC is deliberately never sent to the
   hub.

`utcnow()` returns a **naive** UTC timestamp on purpose: SQLite strips tzinfo on read, and
the audit chain re-hashes stored values, so what goes in must come back out identical.

---

## 4. The five seams

Each one is a single function returning an implementation, so swapping it is one line.

| Seam | File · function | Interface | Ships today | A real implementation |
| --- | --- | --- | --- | --- |
| Extractor | `services/extraction.py::get_extractor` | `Extractor.extract(bytes) -> ExtractedFields` | `MockExtractor`, labelled answers by image SHA-256 | `ClaudeExtractor` is already written: `claude-opus-5-5` vision with an API-enforced JSON schema. No temperature parameter — current Claude models reject sampling parameters, so determinism comes from the enforced schema (decision log 11). |
| Mock vs live extractor | the same function, chosen by `LLM_PROVIDER` | `"mock"` (default) or `"claude"` | mock, so the demo needs no network call | set `LLM_PROVIDER=claude` and `ANTHROPIC_API_KEY`; the official `anthropic` SDK is imported lazily so the mock path never needs it |
| Sender | `services/notify.py::get_sender` | `Sender.send(tenant_id, to_phone, body) -> dict` | `SimulatorSender` — stores an OUT row, `simulated=True` | `CloudApiSender` posts to `graph.facebook.com/v26.0/{phone_id}/messages`. Returned automatically once `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_ID` are both set. **UNVERIFIED against a real Meta account, and free-form text only** — see the gap below. |
| OrbyteConnector | `connectors/orbyte.py::get_connector` | 7 methods, one per assumed endpoint | `MockOrbyteConnector`: real tenant-scoped reads of the local demo data, writes that echo, every dict `"simulated": true` | an HTTP client against the seven endpoints in `/api/orbyte/status`. Those endpoints are **our own documented assumption**: research found no public Orbyte API, sandbox or developer programme ([connect-orbyte.md](connect-orbyte.md)), which the brief allows. |
| Login | `auth/session.py::current_principal` | `Principal(tenant_id, user_id, role, …)` | a signed-cookie role switcher, explicitly allowed by the brief, labelled `simulated_login` on every response | the hub's own session, with roles from `OrbyteConnector.list_users` |

The connector is **on the live path, not decoration** (decision log 20): every receipt is
scored against invoices and customer master data fetched through it, and every approval
calls `record_payment` and `push_activity` and writes a `HUB_SYNCED` audit row.
Deliberately never sent to the hub: the keyed phone HMAC, receipt images, extractions,
match proposals and the audit chain.

**Known gap, logged in the SPEC §12 risk table.** `CloudApiSender` sends free-form text
only. The three chase reminders are business-initiated, so outside Meta's 24-hour
customer-service window they need approved **template** messages; live chasing would fail
loudly. Payment confirmations are replies inside the window, and the simulator the demo
runs on is unaffected.

---

## 5. The audit chain

`app/services/audit.py`. One chain per tenant, ordered by `id`, append-only: there is no
ORM update or delete path for `audit_log` and no endpoint that changes a row.

Each row's `hash_self` is the SHA-256 of these ten fields joined by `|`:

```
hash_prev | tenant_id | actor_type | actor_id | action | entity_type | entity_id
          | before_json | after_json | created_at
```

`None` becomes an empty string, `created_at` is `isoformat()`, and the first row of a
tenant's chain uses `hash_prev = "0" * 64` (`GENESIS`). `verify_chain` walks the rows in
id order, checks each `hash_prev` against the previous row's `hash_self`, recomputes
`row_hash`, and reports the first id that does not match. `/api/audit/export.jsonl` dumps
every field for independent re-verification, and `/api/audit/verify` prints the formula in
its own response.

Two design choices carry the property:

- **`before_json` and `after_json` are canonical JSON *text*, not JSON columns.**
  `canonical()` is `json.dumps(..., sort_keys=True, separators=(",", ":"), default=str)`.
  A JSON column would let SQLAlchemy or SQLite re-serialise the value on read — different
  key order or spacing — and the hash would no longer reproduce byte for byte. Storing the
  exact hashed text removes that whole class of problem.
- **`write_audit` never commits.** It flushes into the caller's transaction, so the audit
  row and the change it records succeed or fail together (CLAUDE.md rule 3). The one
  deliberate exception is `rbac.deny`, which commits because the request is about to fail
  with a 403 and the refused attempt must survive anyway.

`tests/test_audit_chain.py` tampers with rows using raw SQL — the only realistic way a row
could be altered — and asserts verification breaks at the right id.

---

## 6. The frontend

Next.js 16 App Router, React 19, Tailwind 4, `output: 'export'`. Hand-written components
only: no component library, no charting library.

- **`app/layout.jsx`** wraps everything in `Shell`; `app/page.jsx` redirects `/` to
  `/today`; each of the eight screens is a three-line `app/<name>/page.jsx` that does
  `export default screen(Component)`.
- **`components/Shell.jsx`** holds the session, the switchable users, the nav (the `SCREENS`
  array is the demo's running order), the role badges and the honesty footer, and exposes
  `session`, `canApprove`, `goTo`, `refresh` and `version` through a context (`useOrbit`).
  If the API cannot be reached it renders the exact commands to start and seed the backend
  instead of a blank page.
- **`components/Screen.jsx`** is a four-line wrapper: `screen(Component)` pulls the context
  and spreads it as props, so the page components keep the prop signature they were
  written against instead of being rewritten for the router. `key={orbit.version}`
  remounts the screen whenever `refresh()` fires, which is how an approval or a role
  switch refreshes every screen without a store.
- **`components/ui.jsx`** is the entire component kit — `Card`, `Button`, `Badge`, `Table`,
  `Cell`, `Empty`, `Bar`, `Loading`, `ErrorNote`, `SimulatedNote`, plus `toneFor` and
  `humanise`. (Its header comment says "six small pieces"; there are twelve exports. The
  comment is stale, not the code.)
- **`lib/api.js`** is the only file that talks to the backend. One `request()` helper
  (`credentials: 'include'`, JSON unless the body is `FormData`, errors unwrapped from
  FastAPI's `detail`) and one flat `api` object of named calls.
- **Dev vs production.** In `next dev`, `next.config.mjs` adds rewrites proxying `/api`,
  `/v1` and `/webhooks` to `http://127.0.0.1:8000`, so the browser sees one origin exactly
  as it will in production; `NEXT_PUBLIC_API_BASE` can point at the API instead. In
  production `next build` emits static files, `BASE` is empty, and FastAPI serves
  `frontend/out` with `StaticFiles(..., html=True)` mounted last. `trailingSlash: true`
  gives `out/today/index.html`, and `skipTrailingSlashRedirect: true` stops that from
  rewriting `/api/health` to `/api/health/` and breaking every call in development.
  `frontend/out` is gitignored, so a deployment target has to run the build; without it
  the API still works and `/api/health` reports `frontend_built: false`.

---

## 7. Where to start reading

1. **`backend/app/services/proposals.py`** — the whole pipeline in one file.
2. **`backend/app/services/matching.py`** — the scorecard an owner is asked to trust.
3. **`backend/app/services/approval.py`** — the gate, and the one-transaction rule.
4. **`backend/app/services/audit.py`** — 177 lines, and the hash chain is all of it.
5. **`backend/app/connectors/orbyte.py`** — the seam that makes this an Orbyte module
   rather than a standalone app.

Then `frontend/lib/api.js` for the surface the dashboard actually uses.

## 8. What is simulated, and what is not done

Always labelled as simulated: the WhatsApp channel (unless both tokens are set), the
Orbyte hub API, and the login. All data is synthetic.

Not done, and not implied anywhere: no Replit deployment yet (`.replit` and
`scripts/replit-start.sh` are committed and the script parses, but every Replit-specific
line is unverified — and no Replit target has persistent storage, so the SQLite file does
not survive a redeploy; see [connect-replit.md](connect-replit.md)), no demo video, no
pitch deck, no live WhatsApp connection. RunPod is not used at all. [STEPS.md](STEPS.md)
has the build plan state: steps 1–78 and 82–88 done and verified; 79, 80, 81, 89 and 90
open and waiting on owner accounts rather than code.
