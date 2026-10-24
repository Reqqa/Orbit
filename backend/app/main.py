"""Orbit API entrypoint.

Orbit, payment reconciliation for the Orbyte hub.
Run from backend/:  uvicorn app.main:app --reload

In deployment this same process also serves the built dashboard from
frontend/out, so judges only ever need one URL (decision log 8).
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    approvals,
    audit,
    chasing,
    data,
    orbyte,
    session as session_api,
    simulator,
)
from app.config import BACKEND_DIR, get_settings
from app.db import init_db
from app.webhooks import whatsapp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

APP_NAME = "Orbit"
APP_VERSION = "1.0.0"
TAGLINE = "Orbit, payment reconciliation for the Orbyte hub"

# `next build` with output: "export" writes the dashboard here.
FRONTEND_OUT = BACKEND_DIR.parent / "frontend" / "out"

app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description=(
        f"{TAGLINE}.\n\n"
        "Records and reconciles payments that have already happened. Orbit never moves "
        "money, never files anything statutory, and records nothing without a human "
        "approval.\n\n"
        "**What is simulated:** the WhatsApp channel (unless a Cloud API token is set), "
        "the Orbyte hub API, and the login. Every response that depends on one says so. "
        "All data is synthetic.\n\n"
        "`POST /v1/receipts/analyze` is the reusable building block: image in, fields "
        "and match candidates out, nothing recorded."
    ),
)

app.include_router(whatsapp.router)
app.include_router(session_api.router)
app.include_router(approvals.router)
app.include_router(data.router)
app.include_router(audit.router)
app.include_router(chasing.router)
app.include_router(orbyte.router)
app.include_router(simulator.router)


@app.on_event("startup")
def startup() -> None:
    """Create any missing tables. Orbit has no migrations."""
    init_db()
    settings = get_settings()
    if settings.using_placeholder_secrets:
        logging.getLogger("orbit").warning(
            "Running on placeholder secrets. Copy .env.example to .env and set "
            "SESSION_SECRET and PHONE_HMAC_KEY before any real use."
        )


@app.get("/api/health", tags=["system"])
def health() -> dict:
    """Liveness check, and an honest statement of what is simulated right now."""
    settings = get_settings()
    return {
        "status": "ok",
        "name": APP_NAME,
        "version": APP_VERSION,
        "tagline": TAGLINE,
        "demo_mode": settings.demo_mode,
        "timezone": settings.tz,
        "extractor": settings.llm_provider,
        "simulated": {
            "whatsapp_channel": not settings.whatsapp_live,
            "orbyte_api": True,
            "login": True,
        },
        "frontend_built": FRONTEND_OUT.is_dir(),
    }


def _mount_dashboard() -> None:
    """Serve the exported Next.js dashboard, when it has been built.

    Mounted last, so every API route above wins. `html=True` makes Starlette serve
    `today/index.html` for `/today`, which is the layout `next build` produces with
    `trailingSlash: true`.
    """
    if not FRONTEND_OUT.is_dir():
        logging.getLogger("orbit").info(
            "frontend/out not found: API only. Build the dashboard with "
            "`cd frontend && npm run build`."
        )
        return

    app.mount("/", StaticFiles(directory=FRONTEND_OUT, html=True), name="dashboard")


_mount_dashboard()
