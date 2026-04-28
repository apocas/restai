"""WhatsApp Business Cloud API webhook.

Single shared webhook URL routes inbound messages to projects by
``entry[0].changes[0].value.metadata.phone_number_id``. Each project's
HMAC signature is verified against its own ``whatsapp_app_secret``, so
multitenancy is kept honest by per-project secrets rather than by URL
namespacing.

Two endpoints under ``/webhooks/whatsapp``:

* ``GET`` — Meta's subscription handshake. Echoes ``hub.challenge`` when
  ``hub.verify_token`` matches *any* project's stored verify token.
* ``POST`` — inbound message delivery. Verifies the signature, looks up
  the project by phone-number id, runs the agent with
  ``chat_id=f"whatsapp_{from_phone}"``, and posts the reply back via
  Meta's Graph API. Always returns ``200`` within the request — heavy
  work goes to ``BackgroundTasks`` because Meta retries aggressively on
  any non-2xx (or any response taking more than ~10s).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, HTTPException, Query

from restai.auth import get_current_username_project
from restai.database import DBWrapper, get_db_wrapper, open_db_wrapper
from restai.models.databasemodels import ProjectDatabase
from restai.models.models import ChatModel, User
from restai.utils.crypto import decrypt_field
from restai.whatsapp import send_message, verify_signature, validate_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _project_options(proj: ProjectDatabase) -> dict:
    try:
        return json.loads(proj.options) if proj.options else {}
    except Exception:
        return {}


def _find_project_by_verify_token(db, verify_token: str) -> Optional[ProjectDatabase]:
    """Search every project for a matching whatsapp_verify_token. Slow
    O(N) but only runs during the one-time Meta subscription handshake."""
    for proj in db.db.query(ProjectDatabase).all():
        opts = _project_options(proj)
        token = decrypt_field(opts.get("whatsapp_verify_token") or "")
        if token and token == verify_token:
            return proj
    return None


def _find_project_by_phone_id(db, phone_number_id: str) -> Optional[ProjectDatabase]:
    """Look up the project whose whatsapp_phone_number_id matches. The
    field is stored in plaintext (it's not a secret) so we can do a
    direct LIKE filter, then confirm in Python."""
    for proj in db.db.query(ProjectDatabase).all():
        opts = _project_options(proj)
        if (opts.get("whatsapp_phone_number_id") or "") == phone_number_id:
            return proj
    return None


def _parse_allowlist(raw: str) -> set[str]:
    """Same shape as Telegram's allowlist parser, but kept as strings —
    WhatsApp ids are E.164 phone numbers, not ints."""
    out: set[str] = set()
    if not raw:
        return out
    for piece in raw.replace(";", ",").split(","):
        piece = piece.strip().lstrip("+")
        if piece:
            out.add(piece)
    return out


@router.get("/webhooks/whatsapp")
async def verify_webhook(
    request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """Meta's webhook subscription handshake. We echo back ``hub.challenge``
    only when the supplied ``hub.verify_token`` matches one of the
    project-configured verify tokens. Returns 403 otherwise so Meta
    surfaces a clear failure to the admin in Business Suite."""
    if hub_mode != "subscribe" or not hub_challenge or not hub_verify_token:
        raise HTTPException(status_code=400, detail="missing required hub.* params")

    db = open_db_wrapper()
    try:
        proj = _find_project_by_verify_token(db, hub_verify_token)
        if proj is None:
            logger.warning("WhatsApp webhook verify failed — no project matched verify_token")
            raise HTTPException(status_code=403, detail="verify_token mismatch")
        logger.info(f"WhatsApp webhook verified for project '{proj.name}' (id={proj.id})")
        return Response(content=hub_challenge, media_type="text/plain")
    finally:
        db.db.close()


@router.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive inbound WhatsApp messages. Always returns 200 unless the
    signature fails — Meta retries on non-2xx, which would cause
    duplicate messages."""
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256") or request.headers.get("x-hub-signature-256")

    try:
        payload = json.loads(raw or b"{}")
    except Exception:
        logger.warning("WhatsApp webhook received non-JSON body")
        return {"status": "ignored", "reason": "invalid json"}

    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored", "reason": "unexpected object"}

    db = open_db_wrapper()
    try:
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value") or {}
                metadata = value.get("metadata") or {}
                phone_number_id = metadata.get("phone_number_id")
                if not phone_number_id:
                    continue

                proj = _find_project_by_phone_id(db, phone_number_id)
                if proj is None:
                    logger.info(f"WhatsApp inbound for unknown phone_number_id={phone_number_id} — dropping")
                    continue

                opts = _project_options(proj)
                app_secret = decrypt_field(opts.get("whatsapp_app_secret") or "")
                access_token = decrypt_field(opts.get("whatsapp_access_token") or "")

                if not verify_signature(raw, sig, app_secret):
                    logger.warning(
                        f"WhatsApp signature verification FAILED for project '{proj.name}' "
                        f"(id={proj.id}) — possible attacker probe"
                    )
                    raise HTTPException(status_code=401, detail="signature mismatch")

                if not access_token:
                    logger.warning(f"WhatsApp project '{proj.name}' has no access_token — cannot reply")
                    continue

                allowed = _parse_allowlist(opts.get("whatsapp_allowed_phone_numbers") or "")

                for message in value.get("messages", []) or []:
                    background_tasks.add_task(
                        _handle_message_safe,
                        proj.id, phone_number_id, access_token, allowed, message,
                    )

        return {"status": "ok"}
    finally:
        db.db.close()


def _handle_message_safe(project_id: int, phone_number_id: str, access_token: str,
                          allowed: set[str], message: dict) -> None:
    """Background task wrapper — never raises so a single bad message
    can't poison the BackgroundTasks queue."""
    try:
        _handle_message(project_id, phone_number_id, access_token, allowed, message)
    except Exception:
        logger.exception(f"WhatsApp message handler crashed (project={project_id})")


def _handle_message(project_id: int, phone_number_id: str, access_token: str,
                     allowed: set[str], message: dict) -> None:
    msg_type = message.get("type")
    from_phone = (message.get("from") or "").lstrip("+")
    if not from_phone:
        return

    # Allowlist gate — applies to all message types so the polite reply
    # is consistent. Empty allowlist = open access.
    if allowed and from_phone not in allowed:
        logger.info(f"WhatsApp sender {from_phone} not in allowlist for project {project_id}")
        try:
            send_message(
                access_token, phone_number_id, from_phone,
                "You are not authorized to use this bot. "
                f"If you should be, ask the admin to add {from_phone} to the project's allowlist.",
            )
        except Exception as e:
            logger.warning(f"Failed to send unauthorized reply: {e}")
        return

    if msg_type != "text":
        # MVP scope is text-only. Replying once keeps the user from
        # waiting silently for an answer the agent will never produce.
        logger.info(f"WhatsApp inbound type={msg_type!r} from {from_phone} — replying with text-only notice")
        try:
            send_message(
                access_token, phone_number_id, from_phone,
                "Sorry, I can only handle text messages right now.",
            )
        except Exception as e:
            logger.warning(f"Failed to send text-only notice: {e}")
        return

    text = (message.get("text") or {}).get("body") or ""
    if not text.strip():
        return

    logger.info(f"WhatsApp ← {from_phone} (project={project_id}): {text[:200]!r}")

    try:
        response_text = asyncio.run(_run_agent(project_id, text, from_phone))
    except Exception:
        logger.exception(f"Agent dispatch failed for WhatsApp message (project={project_id})")
        return

    if not response_text:
        logger.warning(f"WhatsApp agent returned empty response for project={project_id}")
        return

    try:
        send_message(access_token, phone_number_id, from_phone, response_text)
    except Exception as e:
        logger.warning(f"WhatsApp send failed for project={project_id}: {e}")


async def _run_agent(project_id: int, text: str, from_phone: str) -> Optional[str]:
    """Invoke the project's chat pipeline. Mirrors the Telegram cron's
    helper — same `chat_id=f"<channel>_{user_id}"` convention so each
    customer keeps a sticky conversation across messages."""
    from restai.brain import Brain
    from restai.helper import chat_main
    from fastapi import BackgroundTasks as _BG

    brain = Brain(lightweight=True)
    db = open_db_wrapper()
    try:
        project = brain.find_project(project_id, db)
        if project is None:
            logger.warning(f"_run_agent: project {project_id} not found")
            return None

        chat_input = ChatModel(question=text, id=f"whatsapp_{from_phone}")

        user_db = db.get_user_by_username("admin")
        if user_db is None:
            logger.warning("_run_agent: no 'admin' user — cannot run agent")
            return None
        user = User.model_validate(user_db)

        bg = _BG()
        result = await chat_main(None, brain, project, chat_input, user, db, bg)
        await bg()

        if isinstance(result, dict):
            return result.get("answer", "") or None
        return None
    finally:
        db.db.close()


# ─── Admin: Test Connection ─────────────────────────────────────────────
@router.post("/projects/{projectID}/whatsapp/test")
async def test_whatsapp_connection(
    projectID: int,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Hits Meta's ``GET /{phone_number_id}`` to confirm the project's
    credentials are valid without sending a real message. Surfaces the
    display name + verified status to the admin's "Test Connection"
    button on the project edit page."""
    proj = db_wrapper.get_project_by_id(projectID)
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    opts = _project_options(proj)
    access_token = decrypt_field(opts.get("whatsapp_access_token") or "")
    phone_number_id = opts.get("whatsapp_phone_number_id") or ""
    if not access_token or not phone_number_id:
        return {"ok": False, "error": "WhatsApp is not configured for this project"}
    return validate_token(access_token, phone_number_id)
