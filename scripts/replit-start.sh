#!/usr/bin/env bash
# Orbit, payment reconciliation for the Orbyte hub.
# Replit boot sequence. `.replit` calls this script so the order is reviewable
# here rather than buried in config.
#
# WHAT IS VERIFIED AND WHAT IS NOT
#
# This script was written on a Windows development machine. There is no Replit
# environment here, so the following is HONESTLY UNVERIFIED:
#   - every line that depends on Replit itself: $PORT and $REPL_HOME being set,
#     $REPLIT_DB or Secrets injection, the `.replit` modules providing python3
#     and npm on PATH, and whether the Replit proxy reaches 0.0.0.0:$PORT;
#   - `pip install -r backend/requirements.txt` against Replit's Nix Python
#     (locally the project installs into .venv instead, a different pip target);
#   - the `exec uvicorn ...` line, because it was never started with a
#     Replit-supplied $PORT.
# What WAS verified locally, on Windows:
#   - `bash -n scripts/replit-start.sh` parses with no error;
#   - the seed commands in step 2 and the `npm install && npm run build` in
#     step 3 already run green in this repo;
#   - the staleness comparison in step 3 was exercised against the real
#     frontend/ tree.
# Treat the Replit-specific lines as untested until a judge's Repl has run them.
#
# Secrets come from the Replit environment (Secrets pane). This script never
# reads or creates a committed .env.

set -euo pipefail

# Repo root, whichever directory the script is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

log() { printf '\n== %s\n' "$*"; }

# ---------------------------------------------------------------- 1. Python deps
# Idempotent: pip is a no-op when the requirements are already satisfied.
log "1/4 installing Python dependencies"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r backend/requirements.txt

# --------------------------------------------------- 2. database and demo data
# generate_data --reset drops and recreates every table, so re-running this
# rebuilds the same deterministic data rather than duplicating it.
# generate_receipts rewrites the 50 synthetic PNGs in place (they are
# gitignored; seed/ground_truth.csv, which labels them, is committed).
log "2/4 preparing database and synthetic demo data"
(
  cd backend
  "$PY" -m seed.generate_data --reset
  "$PY" -m seed.generate_receipts
)

# ----------------------------------------------------------- 3. dashboard build
# Skip the build when frontend/out is already newer than every source file
# outside node_modules and out itself, so a restart is fast.
log "3/4 dashboard"
frontend_is_fresh() {
  [ -f frontend/out/index.html ] || return 1
  local newer
  newer="$(find frontend \
      -path frontend/node_modules -prune -o \
      -path frontend/out -prune -o \
      -path frontend/.next -prune -o \
      -type f -newer frontend/out/index.html -print -quit)"
  [ -z "$newer" ]
}

if frontend_is_fresh; then
  echo "frontend/out is newer than the sources: skipping npm install and build"
else
  (
    cd frontend
    npm install
    npm run build
  )
fi

# ------------------------------------------------------------------- 4. serve
# One web process: FastAPI mounts frontend/out at /, so the dashboard and /docs
# are on the same port. exec replaces this shell so uvicorn gets the signals.
log "4/4 serving Orbit on port $PORT (dashboard at /, API docs at /docs)"
cd backend
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
