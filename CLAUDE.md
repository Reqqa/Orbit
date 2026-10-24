# CLAUDE.md — standing rules for this repo

Orbit, payment reconciliation for the Orbyte hub.
The brief this is judged against: `docs/HACKATHON.md`.
Full specification: `docs/SPEC.md`. Build order: `docs/STEPS.md`.
How the code works: `docs/ARCHITECTURE.md`.
How the code fits together: `docs/ARCHITECTURE.md`.

## Naming

- The product is **Orbit**. **Orbyte** is the host business hub, a separate platform that is not us.
- Use the tagline "Orbit, payment reconciliation for the Orbyte hub" so the two are never confused.

## Stack

- Backend: Python 3.12 + FastAPI + SQLAlchemy 2.0 + SQLite, in `backend/`.
- Frontend: Next.js (App Router) + React + Tailwind, in `frontend/`. Static export
  (`output: 'export'`), served by FastAPI, so there is one URL and no Node process
  in production. Hand-written components: no component library, no chart library.
- Runs on Replit. Licence Apache 2.0.
- Only add a dependency to `requirements.txt` when the current step actually needs it.

## Non-negotiables

1. **Money is always integer sen.** RM 850.00 is `85000`. No floats anywhere in money handling.
2. **Every table has `tenant_id` and every query is scoped by tenant.** No endpoint may read across
   tenants.
3. **Every state change goes through a service function that also writes the audit log, in the same
   transaction.** The audit log is append-only and hash-chained; there is no update or delete path.
4. **AI is used for exactly one thing: reading receipt images.** Matching, scoring, classification,
   approval limits and chase scheduling are deterministic rules. Explanations are templated, never
   model prose.
5. **Nothing consequential happens without human approval.** Recording a payment, sending a reminder
   batch, and any write-off or adjustment are all gated by role and amount limit.
6. **Label anything simulated** — the WhatsApp channel, the Orbyte API, the login — in the UI, in API
   responses, and in the README.
7. **Synthetic data only.** Never real personal data, real receipts, real phone numbers or real bank
   accounts. No secrets committed; use `.env` locally and Replit Secrets in deployment.
8. **We never move money.** Orbit records and reconciles payments that already happened. No refunds,
   no statutory filings, no legal or financial advice.
9. **The Orbyte boundary is one-way and explicit.** Hub data — tenant, users and roles, customers,
   open invoices — is read through `OrbyteConnector`, never by a direct query, and an approval writes
   the payment and the activity event back through it. Orbit's own data never crosses to the hub: the
   keyed phone HMAC, receipt images, extractions, match proposals and the audit chain. The hub gets
   decisions, not deliberation.
10. **Four seams, one factory function each.** Extractor (`get_extractor`), Sender (`get_sender`),
    `OrbyteConnector` (`get_connector`) and the login (the session dependency in `auth/session.py`).
    Each returns an implementation and is the only place that chooses one, so swapping mock for real
    is a one-line change and no caller moves.

## How to work

- Keep the code simple and boring. The demo must work every time. No over-engineering.
- Work one step at a time, in the order given by `docs/STEPS.md`. Do not start a step until the
  previous step's "done when" check passes.
- After each step, state exactly how to check it works.
- Tests only for matching and classification, RBAC, and the audit hash chain. No tests for the UI,
  the webhook, the seed scripts or anything else.
- Never fake results. If something is simulated, say so. Keep the README honest, including the
  failures in the accuracy numbers.
- Where the spec is ambiguous, pick the simplest option that keeps the demo reliable.
- Record spec changes in the Decision Log, `docs/SPEC.md` section 21.
