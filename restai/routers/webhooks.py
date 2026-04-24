"""Admin endpoint for testing project event webhooks.

Single ``POST /projects/{id}/webhooks/test`` route — fires a synthetic
``test`` event so an admin can confirm their receiver is wired
correctly without waiting for a real budget/sync/eval/routine event.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from restai.auth import get_current_username_project
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User
from restai.webhooks import emit_event

router = APIRouter()


@router.post("/projects/{projectID}/webhooks/test")
async def test_webhook(
    projectID: int,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Fire a synthetic ``test`` event to the project's webhook URL.
    Returns ``{ok: bool, reason?: str}``. ``ok=False`` when no URL is
    configured, the URL is unsafe (private/internal), or the event
    isn't in the project's subscribed set."""
    proj = db_wrapper.get_project_by_id(projectID)
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        opts = json.loads(proj.options) if proj.options else {}
    except Exception:
        opts = {}
    if not (opts.get("webhook_url") or "").strip():
        return {"ok": False, "reason": "no webhook_url configured"}
    queued = emit_event(
        projectID, proj.name, opts, "test",
        {"message": "RESTai test webhook — receiver is reachable."},
    )
    if not queued:
        return {"ok": False, "reason": "event filtered or url refused (check logs)"}
    return {"ok": True}
