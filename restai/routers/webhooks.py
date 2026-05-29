"""Admin endpoints for project event webhooks: test fire + secret rotate."""
from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException

from restai.auth import get_current_username_project
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User
from restai.utils.crypto import encrypt_field
from restai.comms.webhooks import emit_event

router = APIRouter()


@router.post("/projects/{projectID}/webhooks/test")
async def test_webhook(
    projectID: int,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Fire a synthetic ``test`` event to the project's webhook URL."""
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


@router.post("/projects/{projectID}/webhooks/rotate-secret")
async def rotate_webhook_secret(
    projectID: int,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Mint + encrypt a new signing secret; returns plaintext once."""
    proj = db_wrapper.get_project_by_id(projectID)
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        opts = json.loads(proj.options) if proj.options else {}
    except Exception:
        opts = {}
    plaintext = secrets.token_urlsafe(32)
    opts["webhook_secret"] = encrypt_field(plaintext)
    proj.options = json.dumps(opts)
    db_wrapper.db.commit()
    return {"secret": plaintext}
