"""Outbound event webhooks for projects.

Per-project: when an admin sets ``webhook_url`` on a project, RESTai POSTs
JSON event payloads to that URL whenever interesting things happen
(budget exhausted, sync finished, eval finished, routine failed). Lets
SMBs wire RESTai into Zapier / n8n / custom CRMs without scraping the
audit log.

* **One shared signature scheme** — every payload is signed with
  HMAC-SHA256 of the raw body keyed on the project's ``webhook_secret``;
  the digest goes in the ``X-RESTai-Signature`` header as
  ``sha256=<hexdigest>``. Same shape Meta uses for WhatsApp, GitHub uses
  for repos — keeps receiver code reusable.
* **Fire-and-forget** — POSTs run in a background thread with a 10s
  timeout. We log non-2xx responses but never raise into the caller, so
  a flaky receiver can't break inference / cron / eval flows.
* **Subscription filter** — projects can opt into a subset of events via
  the ``webhook_events`` CSV. Empty/missing = subscribe to everything.
* **SSRF guard** — webhooks must point at a public host. Loopback /
  RFC1918 / link-local destinations are refused (matches the SSRF
  guards on `crawler_classic` and `_sync_url`). An admin who needs to
  test against localhost has to do it through a tunnel anyway since
  worker processes don't share localhost.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from restai.helper import _is_private_ip
from restai.utils.crypto import decrypt_field

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = {
    "budget_exceeded",
    "sync_completed",
    "eval_completed",
    "routine_failed",
    "test",  # synthetic event the admin Test button fires.
}


def _project_webhook_config(opts: dict) -> tuple[str, str, set[str]]:
    """Pull (url, secret, allowed_events) out of a project options blob.
    Returns ('', '', set()) when the project hasn't configured webhooks
    so callers can early-exit cheaply."""
    url = (opts.get("webhook_url") or "").strip()
    if not url:
        return "", "", set()
    secret = decrypt_field(opts.get("webhook_secret") or "")
    raw_events = (opts.get("webhook_events") or "").strip()
    if raw_events:
        events = {e.strip() for e in raw_events.replace(";", ",").split(",") if e.strip()}
    else:
        # Empty = subscribe to everything supported.
        events = set(SUPPORTED_EVENTS)
    return url, secret, events


def _safe_url(url: str) -> Optional[str]:
    """Return the URL only if it's safe to fetch (https? scheme + public
    hostname). Returns None and logs a warning otherwise."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        logger.warning("webhook url has unsupported scheme: %r", url)
        return None
    hostname = parsed.hostname
    if not hostname:
        logger.warning("webhook url has no hostname: %r", url)
        return None
    try:
        if _is_private_ip(hostname):
            logger.warning("refusing to POST webhook to private/internal address: %s", hostname)
            return None
    except ValueError as e:
        logger.warning("webhook url unresolvable: %s", e)
        return None
    return url


def _post_in_thread(url: str, body: bytes, headers: dict) -> None:
    def _go():
        try:
            resp = requests.post(url, data=body, headers=headers, timeout=10)
            if resp.status_code >= 400:
                logger.warning("webhook POST returned HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("webhook POST failed: %s", e)
    threading.Thread(target=_go, daemon=True).start()


def emit_event(project_id: int, project_name: str, opts: dict,
               event_type: str, data: Any) -> bool:
    """Send an event webhook for one project.

    Args:
        project_id: numeric project id
        project_name: project name (included in payload for receiver UX)
        opts: the project's options dict (already JSON-decoded)
        event_type: one of SUPPORTED_EVENTS
        data: event-specific payload (must be JSON-serializable)

    Returns ``True`` when a request was queued, ``False`` when it was
    skipped (no url configured, event filtered out, or unsafe url).
    """
    if event_type not in SUPPORTED_EVENTS:
        logger.warning("emit_event: unknown event_type %r — refusing to send", event_type)
        return False

    url, secret, events = _project_webhook_config(opts)
    if not url:
        return False
    if event_type not in events:
        return False
    safe = _safe_url(url)
    if not safe:
        return False

    payload = {
        "event": event_type,
        "project_id": project_id,
        "project_name": project_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "RESTai-Webhook/1.0",
        "X-RESTai-Event": event_type,
    }
    if secret:
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-RESTai-Signature"] = f"sha256={sig}"

    _post_in_thread(safe, body, headers)
    return True


def emit_event_for_project_id(project_id: int, event_type: str, data: Any) -> bool:
    """Convenience wrapper that fetches the project options from the DB
    itself. Use this from places (cron jobs, BackgroundTasks) that
    don't already hold a project handle. Returns True/False like
    ``emit_event``."""
    try:
        from restai.database import open_db_wrapper
    except Exception:
        return False
    db = open_db_wrapper()
    try:
        proj = db.get_project_by_id(int(project_id))
        if proj is None:
            return False
        try:
            opts = json.loads(proj.options) if proj.options else {}
        except Exception:
            opts = {}
        return emit_event(proj.id, proj.name, opts, event_type, data)
    finally:
        db.db.close()
