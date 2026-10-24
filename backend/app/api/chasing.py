"""Chasing: preview tomorrow's batch, then approve it (docs/SPEC.md section 9.4)."""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.auth.rbac import APPROVE_BATCH, VIEW_ALL, require
from app.auth.session import Principal
from app.db import get_session
from app.services import chasing

router = APIRouter(prefix="/api/chasing", tags=["chasing"])


@router.get("/batch/tomorrow")
def preview_batch(
    principal: Principal = Depends(require(VIEW_ALL)),
    session: Session = Depends(get_session),
) -> dict:
    """Drafts already waiting. Nothing is sent and nothing new is drafted."""
    return chasing.pending_batch(session, tenant_id=principal.tenant_id)


@router.post("/run-now")
def run_now(
    principal: Principal = Depends(require(APPROVE_BATCH)),
    session: Session = Depends(get_session),
) -> dict:
    """Recalculate today's ladder. This is the daily job, triggered by hand."""
    return chasing.build_batch(session, tenant_id=principal.tenant_id)


@router.post("/batch/{batch_date}/approve")
def approve_batch(
    batch_date: str,
    payload: dict = Body(default={}),
    principal: Principal = Depends(require(APPROVE_BATCH)),
    session: Session = Depends(get_session),
) -> dict:
    """Send the drafts the owner kept. `batch_date` is the preview they looked at."""
    return chasing.approve_batch(
        session,
        tenant_id=principal.tenant_id,
        approver_id=principal.user_id,
        reminder_ids=[int(i) for i in payload.get("reminder_ids", [])],
        skip_ids=[int(i) for i in payload.get("skip_ids", [])],
    )
