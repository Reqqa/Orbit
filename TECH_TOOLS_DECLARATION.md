# Tech tools declaration

Orbit, payment reconciliation for the Orbyte hub. S.D.C. Hackathon 2026.

This file answers the submission checklist item in `docs/SPEC.md` section 18: every tool,
model, API and library actually used, and where AI assistance was used. Versions below are
copied from `backend/requirements.txt` and `frontend/package.json` as they stand in the repo.
Those files use minimum or caret constraints rather than exact pins, with one exception
(`httpx==0.28.1`), so each line gives the constraint from the file and, where it is useful,
the version actually resolved in the development environment. Every version below was
re-checked against `backend/requirements.txt`, `frontend/package.json` and `pip list`.

---

## 1. Languages and runtimes

| Thing | Version | Notes |
|---|---|---|
| Python | 3.12 (3.12.10 locally) | Backend, seed scripts, tests |
| Node.js | 26.4.0 locally, npm 11.11.0 | Build tool only. Used to produce the static export; no Node process runs in production |
| Next.js | `^16.4.3` (`frontend/package.json`) | App Router, `output: 'export'` |
| React | `^19.3.1` | With `react-dom` `^19.3.1` |
| SQLite | Python stdlib `sqlite3` via SQLAlchemy | Single file `backend/orbit.db`, 11 tables, no migrations |

---

## 2. Backend libraries

All from `backend/requirements.txt`. One line each, what it is actually for.

| Library | Constraint in file | Resolved | What it does here |
|---|---|---|---|
| fastapi | `>=0.115` | 0.162.0 | The HTTP API, request validation wiring, and serving the built frontend from one URL |
| uvicorn[standard] | `>=0.32` | 0.54.0 | The ASGI server the app runs under |
| sqlalchemy | `>=2.0.36,<2.1` | 2.0.55 | ORM and session/transaction handling for the 11 tables; every state change plus its audit row commits in one transaction |
| pydantic | `>=2.9` | 2.14.1 | Request and response schemas, and validating extracted receipt fields |
| pydantic-settings | `>=2.6` | 2.16.1 | Loads configuration and secrets from `.env` or the environment (`LLM_PROVIDER`, keys, `DEMO_MODE`) |
| python-multipart | `>=0.0.12` | 0.0.32 | Parses multipart uploads, that is, the receipt image posted by the WhatsApp simulator |
| cryptography | `>=43.0` | 50.0.2 | Fernet encryption of the stored phone-number copy used to send replies. The lookup HMAC and the session cookie signature use the stdlib `hmac`, not this library |
| rapidfuzz | `>=3.10` | 3.14.6 | Payer-name similarity, one component of the match scorecard |
| pillow | `>=11.0` | 13.0.0 | Draws the 50 synthetic receipt PNGs in the seed step |
| anthropic | `>=1.0` | 2.3.0 | The Claude API SDK. Imported lazily inside the Claude extractor, so the default mock path never needs it |
| httpx | `==0.28.1` | 0.28.1 | The HTTP client for the live WhatsApp Cloud API path in `backend/app/services/notify.py`: sending a text message, and the two-step inbound media download in `backend/app/webhooks/whatsapp.py`. It arrived anyway as a transitive dependency of the `anthropic` SDK; it is pinned exactly so a fresh deployment cannot resolve a different version by accident. Imported lazily, so the simulator path does not need it at import time |
| pytest | `>=8.3` | 9.1.1 | The 42 tests: matching, classification, duplicate recording, RBAC, audit hash chain. Nothing else is tested |

No other backend dependency is used. No OCR engine, no ML framework, no task queue, no
message broker, no Redis, no Postgres, no Docker.

---

## 3. Frontend

All from `frontend/package.json`.

| Package | Constraint in file | What it does here |
|---|---|---|
| next | `^16.4.3` | App Router pages for the 8 screens; `next build` produces the static export in `frontend/out` |
| react | `^19.3.1` | The components |
| react-dom | `^19.3.1` | Browser rendering |
| tailwindcss | `^4.3.3` (devDependency) | All styling |
| @tailwindcss/postcss | `^4.3.3` (devDependency) | The Tailwind 4 PostCSS plugin |
| postcss | `^8.5.31` (devDependency) | Runs that plugin during the build |

**No component library and no charting library are used.** There is no shadcn/ui, no MUI,
no Radix, no Chart.js, no Recharts, no D3. Every control, table, badge and panel in
`frontend/components/` is hand-written, and the bars on the dashboard are hand-written divs
with a width percentage. The only runtime dependencies shipped to the browser are React and
Next.js itself.

FastAPI serves `frontend/out` in production, so there is one URL and no Node runtime
deployed. The dev server proxies `/api`, `/v1` and `/webhooks` to the Python process so the
browser sees the same single origin it will see in production.

---

## 4. AI models

| Item | Detail |
|---|---|
| Model | `claude-opus-5-5` |
| Access | Anthropic API, via the official `anthropic` Python SDK (`>=1.0`, resolved 2.3.0) |
| Used for | Exactly one thing: reading a receipt image and returning its fields as JSON (`backend/app/services/extraction.py`) |
| Default state | **Off.** `LLM_PROVIDER=mock` is the default in `.env.example`. The mock extractor looks the answer up by image SHA-256 in `backend/seed/ground_truth.csv`, so the demo makes no network call and needs no API key |
| Live mode | `LLM_PROVIDER=claude` with `ANTHROPIC_API_KEY` set switches to real Claude vision. One retry, then the receipt is routed to a human |

Everything else is deterministic Python with no model involved: the 100-point match
scorecard, the 8 classifications, the role and amount-based approval limits, the
`-3/+1/+7/+14` chase ladder, and all customer-facing message text, which comes from fixed
templates in `backend/app/templates/`. No model writes prose that a customer or an approver
sees.

The extraction call is constrained by an API-enforced JSON schema
(`output_config={"format": {"type": "json_schema", ...}}`) plus a literal prompt, **not** by
`temperature=0`. `docs/SPEC.md` section 7.1 originally asked for temperature 0; current
Claude models reject sampling parameters outright, so the enforced response schema replaces
it (decision log 11).

No other model and no other model provider is used anywhere in the product. No embeddings,
no vector database, no RAG, no fine-tuning, no self-hosted or local model weights.

---

## 5. Simulated or assumed interfaces

These three are simulated in everything a judge will run. Each is labelled as simulated in
the UI, in the API responses and in the README.

| Interface | What exists | What does not |
|---|---|---|
| WhatsApp Cloud API | A built-in simulator that posts payloads in the same Meta webhook shape the real Cloud API sends, handled by `backend/app/webhooks/whatsapp.py`. Outbound confirmations and reminders are rendered from templates and recorded, not transmitted. Alongside it, a real Cloud API path **is now implemented** (see below) | No connection to Meta. There is no Meta or WhatsApp Business account on the development machine, no phone number ID and no approved message template, so the live code has never been run against `graph.facebook.com` |
| Orbyte hub API | `OrbyteConnector` in `backend/app/connectors/orbyte.py`, on the live decision path, with `MockOrbyteConnector` reading the local synthetic data (see below) | Orbyte published no API, sandbox or developer programme for this (`docs/connect-orbyte.md`). The seven endpoints Orbit assumes are **our own documented assumption**, which the brief allows, not a specification we were given, and the real one may differ |
| Login | A signed-cookie role switcher (`backend/app/auth/session.py`) that picks a seeded user so judges can switch between Sales, Finance and Owner. RBAC itself is real and enforced server-side: Sales attempting to approve gets HTTP 403 and the attempt is written to the audit log | No passwords, no identity provider, no SSO, no OAuth, no real authentication of any kind |

### 5.1 WhatsApp: what the live path does, and the one gap

`backend/app/services/notify.py` has two senders behind one interface. `get_sender()`
returns `CloudApiSender` when **both** `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_ID` are set, and
`SimulatorSender` otherwise. Four settings, all optional: `WHATSAPP_TOKEN`,
`WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`.

| Point | Detail |
|---|---|
| Outbound | `CloudApiSender` POSTs to `graph.facebook.com/v26.0/{phone_id}/messages` with httpx. The version lives in one constant, `GRAPH_API_VERSION`, which the webhook imports so the send and media paths cannot drift |
| Inbound media | Images are downloaded from Meta by media id in two steps and saved with `app.media.save_media`, so the extraction cache and the dashboard image behave exactly as they do for the simulator |
| How it was checked | Both `get_sender()` branches, and the request the sender builds, were verified by injecting a fake `http_post`. The 40 tests still pass and the simulator path is unchanged. **Not** verified against Meta |
| Known gap | `CloudApiSender` sends free-form text only. The three chase reminders are business-initiated, so outside Meta's 24-hour customer service window they require approved **template** messages. Live chasing would therefore fail loudly. Payment confirmations are replies inside the window and are unaffected; the simulator, which is what the demo uses, is unaffected. Logged in the `docs/SPEC.md` section 12 risk table |

Without the two tokens, `CloudApiSender.send()` raises `NotImplementedError` as a guard. The
guard is not the live path: with the tokens set, the real request is built and sent.

### 5.2 Orbyte: the connector is on the live decision path

The connector is not decoration beside the real logic; it **is** how Orbit sees hub data
(decision log 20).

- Every receipt is scored against invoices **and** customer master data fetched through
  `OrbyteConnector` in `backend/app/services/proposals.py`, not by a direct query.
- Every approval in `backend/app/services/approval.py` calls `record_payment` with the
  idempotency key `orbit-proposal-<id>` and `push_activity`, then writes a `HUB_SYNCED` audit
  row in the same transaction.
- `backend/app/api/orbyte.py` is a module in its own right, exposing
  `GET /api/orbyte/status` (the live connector class, what it can currently see, and the
  seven assumed endpoints) and `GET /api/orbyte/preview` (the raw records).
- Every response from `MockOrbyteConnector` carries `"simulated": true`.
- Deliberately **not** sent to the hub: the keyed phone HMAC, receipt images, extractions,
  match proposals and the audit chain.

---

## 6. AI coding assistance

**Claude Code (Claude Opus 5) was used throughout to write and review this codebase.** To be
specific about the extent:

- Nearly all of the committed Python and JavaScript was written by Claude Code from
  `docs/SPEC.md` and `docs/STEPS.md`, under the standing rules in `CLAUDE.md`, step by step,
  with a human reviewing and directing each step.
- Parallel Claude Code subagents were used for work that split cleanly: the backend service
  modules under `backend/app/services/`, the dashboard screens under `frontend/app/` and
  `frontend/components/`, and the documentation set.
- This declaration was itself written by a Claude Code subagent, which read
  `backend/requirements.txt`, `frontend/package.json` and `pip list` output for the versions
  above rather than recalling them from memory, and re-checked them after later changes.
- The specification, the architecture decisions, the scoring weights and thresholds, the
  classification set and the honesty rules were decided by the human team. Claude Code
  implemented them and was corrected where it drifted.
- Claude Code also wrote the 40 pytest tests. They were run, not assumed: the suite and the
  end-to-end journey were executed before each step was accepted.

This is separate from section 4. Claude Code is a development-time assistant and ships
nothing. The only model in the running product is the receipt extractor, and it is off by
default.

---

## 7. Infrastructure

| Item | Status |
|---|---|
| Replit | The intended host, and the design assumes it: FastAPI serves the static export so a single Replit web service covers the whole app, and secrets belong in Replit Secrets rather than a committed `.env`. **No deployment has been made at the time of writing.** A `.replit` file and `scripts/replit-start.sh` are committed and the script parses, but every Replit-specific line in them is unverified. Researched limits are in `docs/connect-replit.md`: no Replit deployment target has persistent storage, so the SQLite file does not survive a redeploy (the boot script reseeds, so it self-heals, but judge clicks are lost); Reserved VM is the only target suited to a single SQLite file and is paid, from about USD 15/month; the free Starter plan allows one published app, which expires after 30 days. That doc recommends recording the video against the free development URL and publishing only if a persistent link is required. Proof-of-Replit screenshots and a deployment URL are still outstanding |
| RunPod | **Not used at all.** No self-hosted model is part of this build, so there is no GPU workload to run anywhere: receipt extraction is either the offline mock lookup or the hosted Anthropic API. Claiming RunPod utilisation would be false, and `docs/SPEC.md` section 18 asks for that proof only if the tool was truly used |
| Everything else | Runs locally on one machine: one Python process and one SQLite file. No containers, no cloud services, no external database. The only third-party services the running product can call are the Anthropic API, in the optional live-extraction mode, and the Meta Graph API, in the optional live WhatsApp mode. In the default demo configuration it calls neither |

Licence: Apache 2.0 (`LICENSE` in the repo root).

---

## 8. Data

100 per cent synthetic, generated by the seed scripts committed in `backend/seed/`:

- 3 tenants, 9 users, 75 customers and 80 invoices, produced from a deterministic seed so
  the same run gives the same data.
- 50 receipt images drawn by Pillow, covering all 8 classifications, labelled in
  `backend/seed/ground_truth.csv`. The CSV is committed; the generated PNGs are gitignored
  and are rebuilt by running the seed step. The redraw is byte-identical (verified 50/50),
  and the CSV keys each image by SHA-256, so the committed labels keep working in a fresh
  clone.

No real personal data, no real receipts, no real phone numbers, no real bank or account
details, and no customer data from any business. Nothing in this repository was derived from
a real payment. No API keys or secrets are committed; `.env.example` holds placeholders only.
