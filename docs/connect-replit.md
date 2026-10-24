# Deploying Orbit to Replit

What this gets you: one public URL where a judge sees the dashboard at `/`, the API
docs at `/docs`, and a health check at `/api/health`.

Two things to know before you start, because they change what you do:

- **Orbit stores data in a local SQLite file.** Replit's published apps do not keep
  filesystem data. See step 12 — it is not a blocker, but you need to know it.
- **Nothing below has been run.** There is no Replit environment on your dev machine,
  so `.replit` and `scripts/replit-start.sh` are written but untested. Steps marked
  **(verify in the console)** are ones I could not confirm from Replit's docs.

---

## A. Import the repo

**1. Push your work to GitHub first.** Replit imports from GitHub, not from your disk.
The import copies files but **not** secret values, so you will set those by hand in
step 4.
Source: <https://docs.replit.com/build/import-from-github>

**2. Import it.** Two ways, both current:

- Public repo, fastest: open `https://replit.com/github.com/<you>/Orbit` and press Enter.
- Private repo, or you want the dialog: go to <https://replit.com/import>, choose
  **GitHub**, connect your GitHub account, pick the repo, select **Import**.

**3. Let it finish, then do not trust the run command it guessed.** Open `.replit` in
the file tree and confirm it still says:

```toml
modules = ["python-3.12", "nodejs-20"]
run = ["bash", "scripts/replit-start.sh"]
```

Replit's importer sometimes rewrites the run command. If it did, put that line back.
**(verify in the console)** — Replit's config reference documents the `modules` key but
its only example is an old pinned identifier (`python-3.10:v18-...`), so I cannot
confirm the bare `python-3.12` / `nodejs-20` spellings are accepted. If boot fails at
step 7 with "python3: not found" or "npm: not found", that is this. Fix: open
**Tools → Dependencies** and add the Python 3.12 and Node.js 20 modules through the UI,
which writes the correct identifiers for you.
Source: <https://docs.replit.com/references/project-setup/configuration.md>

---

## B. Secrets

**4. Open the Secrets pane:** in the project, **Tools** (top of the editor) → **Secrets**,
under the **Setup** heading. Select **New Secret**, enter the Key and Value, select
**Add Secret**. Each one becomes an environment variable your code reads normally.
Source: <https://docs.replit.com/replit-workspace/workspace-features/secrets>

**5. Set these two. Orbit will not start without them.**

| Key | Value |
|---|---|
| `SESSION_SECRET` | a long random string |
| `PHONE_HMAC_KEY` | a different long random string |

Generate both on your Windows machine (PowerShell), then paste:

```powershell
C:\Users\User\Documents\GitHub\Orbit\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Run it twice. Use the first output for `SESSION_SECRET`, the second for
`PHONE_HMAC_KEY`. Do not reuse one value for both.

**6. These are optional. Skip them for the demo.**

| Key | Set it to | Why |
|---|---|---|
| `LLM_PROVIDER` | leave unset, or `mock` | `mock` reads labelled answers from `seed/ground_truth.csv` and makes no network call. This is what you want for a demo that works every time. |
| `PHONE_ENC_KEY` | a Fernet key | Only needed if you exercise the encrypted-phone path. |
| `ANTHROPIC_API_KEY` | your key | Only read when `LLM_PROVIDER=claude`. Setting it while `LLM_PROVIDER` is `mock` does nothing. |

If you do want `PHONE_ENC_KEY`:

```powershell
C:\Users\User\Documents\GitHub\Orbit\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Do not put any of these in a file in the repo. `.env` is gitignored and the boot script
never reads one.

---

## C. Boot

**7. Press Run.** `scripts/replit-start.sh` does four things, in order:

1. `pip install -r backend/requirements.txt`
2. Seeds the database and regenerates the 50 synthetic receipt PNGs
   (`seed.generate_data --reset`, `seed.generate_receipts`)
3. Builds the dashboard with `npm install && npm run build` — **skipped** if
   `frontend/out` is already newer than every frontend source file
4. `exec uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**8. Expect the first boot to take a few minutes**, most of it step 3 (`npm install`
plus the Next.js static export). Later restarts are much faster, because step 3 is
skipped and pip is a no-op. I cannot give you a real number — nobody has timed this on
Replit hardware.

---

## D. Confirm it worked

**9. Open the Preview pane** (formerly called Webview). Replit maps your port 8000 to
external port 80, which is what the `[[ports]]` block in `.replit` does, so the app
loads at the root of the URL. 8000 is on Replit's documented forwardable-port list.
Source: <https://docs.replit.com/features/project-setup/ports>

**10. Check three URLs**, in this order:

1. `/api/health` — must show `"frontend_built": true`. If it says `false`, the dashboard
   build did not produce `frontend/out` (see step 17).
2. `/` — the dashboard.
3. `/docs` — the FastAPI interactive API docs.

If `/api/health` answers but `/` gives a 404, the API is up and only the frontend build
failed. That is a step-17 problem, not a port problem.

**11. Click the journey through once:** Simulator → upload a receipt → Approvals →
Approve. Same path as `docs/demo-script.md`.

---

## E. The SQLite consequence — read this one

**12. Your data does not survive a redeploy, on any published target.** Replit's docs
state that Autoscale, Static and Reserved VM deployments have no persistent storage and
that data written to the filesystem will not persist after redeploying. The persistent
options they offer instead are Object Storage, PostgreSQL and ReplDB.
Source: <https://docs.replit.com/hosting/deployments/about-deployments>

Whether a Reserved VM keeps `orbit.db` across a plain **restart** (as opposed to a
redeploy) is not documented either way. **(verify in the console)** — assume it does not.

**13. This is survivable, and here is why:** the boot script runs
`seed.generate_data --reset` on every start. `--reset` drops and recreates every table
and rebuilds the same deterministic synthetic data. So a wiped database self-heals into
a clean, identical demo on the next boot.

**What that costs you:** any approval a judge clicks is gone after a restart or a
redeploy. The demo always starts from the same state. For a hackathon demo this is a
feature, not a bug — but do not claim Orbit persists data on Replit, because on a
published target it does not.

**14. Which target to use.** Deployment type is chosen in the **Publishing** tool →
**Adjust settings** → **Deployment type**, and that UI is authoritative — it rewrites
`.replit` for you. Our file commits `deploymentTarget = "vm"`. **(verify in the
console)**: Replit's config reference does not list the valid values for
`deploymentTarget` at all, and the only example it gives is `cloudrun`, so I cannot
confirm `"vm"` is the right string for Reserved VM. Set the type in the dropdown and let
it write the file.

Prices, from Replit's own pricing page
(<https://docs.replit.com/billing/deployment-pricing.md>):

- **Reserved VM** — paid. Shared 0.5 vCPU / 2 GB is **$15.00/month**; 1 vCPU / 4 GB is
  $35.00/month. This is the type Orbit wants (single long-lived instance, local file).
- **Autoscale** — $2/month base, plus $0.60 per million compute units and $0.40 per
  million requests. Cheaper, but it scales to zero and can run more than one instance,
  which is wrong for a single SQLite file.
- **Static** — free hosting, $0.05/GB transfer. Useless here: Orbit needs Python.
- **Starter (free) plan** — includes **1 free published app, which expires after 30 days**
  and can be re-published. The page does not say which deployment types that free slot
  covers, so do not assume it covers a Reserved VM. **(verify in the console)**

**15. Development URL vs Deployment URL.** These are different things:

- The **development URL** (`UUID.servername.replit.dev`) is the Preview pane's address.
  It is live only while you are actively working in the app, and it can change each time
  you reopen the project. Replit calls it temporary and for testing only.
  Source: <https://docs.replit.com/core-concepts/workspace/app-setup/development-urls>
- The **Deployment URL** is a separate published instance, built from a snapshot. New
  code does not reach it until you publish again.
  Source: <https://docs.replit.com/hosting/deployments/about-deployments>

**(verify in the console)** — sources disagree on whether development URLs are public.
Replit's own development-URLs page currently says they are **private and require
authentication**; other copies of Replit's docs say they are public by default with a
"Private development URL" toggle under **Networking** in the developer tools. Check that
toggle yourself before you send a link to anyone. If the dev URL turns out to require
sign-in, a judge cannot open it and you must publish.

**My recommendation:** record your video against the development URL (free, works, no
billing decision), and publish only if the submission needs a link that stays up. Then
keep in mind the 30-day expiry on the free slot — publish close to judging, not weeks
early.

---

## F. Proof of Replit utilization

`docs/SPEC.md` §18 asks for "Proof of Replit utilization (screenshots/deployment URL)".
`docs/proof/` exists and is empty. Save PNGs there with these names:

**16. Take five screenshots.** Each must have the `replit.dev` or `replit.app` URL
visible in the browser address bar, or the Replit editor chrome visible — that is the
whole point of the proof.

| Save as | What to capture |
|---|---|
| `docs/proof/replit-01-editor.png` | The Replit editor with the Orbit file tree open |
| `docs/proof/replit-02-console.png` | The console showing the four boot steps and `4/4 serving Orbit on port ...` |
| `docs/proof/replit-03-dashboard.png` | The dashboard at `/`, URL bar visible |
| `docs/proof/replit-04-health.png` | `/api/health` showing `"frontend_built": true` |
| `docs/proof/replit-05-docs.png` | `/docs`, the FastAPI docs page |

**Do not screenshot the Secrets pane** with values revealed. If you want proof that
secrets were used, capture the pane with the keys listed and values hidden, as
`docs/proof/replit-06-secrets.png`.

Then put the live URL in the README and the submission form.

---

## G. Troubleshooting what you will actually hit

**17. Dashboard 404s, or `/api/health` says `"frontend_built": false`.**
`frontend/out` is gitignored, so it is never imported — it must be built on Replit.
Either the build failed or the staleness check wrongly skipped it. Force a rebuild in
the Replit Shell:

```bash
rm -rf frontend/out && bash scripts/replit-start.sh
```

If `npm run build` errors, read the error: Tailwind and Next are pinned in
`frontend/package.json` and build green locally, so a failure here is environmental.

**18. `npm install` or `npm run build` is killed / "out of memory".**
Shared Reserved VM is 0.5 vCPU / 2 GB, and a Next.js build can exceed that. Options, in
order of preference:

1. Build it locally on Windows, then commit `frontend/out` by removing the
   `frontend/out/` line from `.gitignore`. The boot script's staleness check will then
   skip the build entirely. Ugly, reliable, and the fastest boot you will get.
2. Cap Node's heap in the Shell before rerunning:
   `NODE_OPTIONS=--max-old-space-size=1536 npm run build`
3. Move up a VM size ($35/month).

**19. "The port is not being detected" / the Preview stays blank.**
Three causes, check in order:

1. Uvicorn must bind `0.0.0.0`, not `localhost`. The boot script already passes
   `--host 0.0.0.0`; if you changed it, change it back. Replit's docs are explicit that
   an Autoscale or Reserved VM internal port must not be localhost.
2. The `[[ports]]` block must map to `externalPort = 80`. Replit's Reserved VM docs say
   that if ports are configured in `.replit`, one must use `externalPort = 80`. Ours
   does.
3. `$PORT` mismatch. The script uses `${PORT:-8000}`, so if Replit injects a different
   `$PORT`, uvicorn follows it but `.replit` still maps `localPort = 8000` — and nothing
   is listening on 8000. Fix: in the Shell, run `echo $PORT`. If it is not 8000, edit
   `.replit` so `localPort` matches it.
   Source: <https://docs.replit.com/features/project-setup/ports>

**20. A missing secret.** The app fails at startup with a config error naming the key.
Confirm the secret exists and is spelled exactly `SESSION_SECRET` / `PHONE_HMAC_KEY` —
in the **Shell**, run `printenv | grep -E 'SESSION_SECRET|PHONE_HMAC_KEY'` and check the
names come back (it prints the values too, so don't do this on a shared screen). If a
secret you added is not there, stop and restart the app; Secrets are injected at process
start. Note that a published app has its own **Production app secrets** under
**Publishing → Adjust settings** — adding a secret in the editor does not necessarily
put it on the published instance. **(verify in the console)**
Source: <https://docs.replit.com/replit-workspace/workspace-features/secrets>

**21. Changing `PHONE_HMAC_KEY` later invalidates every stored `phone_hmac`.** Since the
boot script reseeds anyway, this fixes itself on the next restart — but don't rotate that
key mid-demo.
