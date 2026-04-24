"""WhatsApp Business Cloud API client.

Three things:
1. `verify_signature(raw_body, sig_header, app_secret)` — Meta signs every
   inbound webhook with HMAC-SHA256 of the raw request body keyed on the
   app secret. We must verify on the *raw* bytes, not the parsed JSON,
   because any whitespace/key-order difference breaks the digest.
2. `send_message(access_token, phone_number_id, to, text)` — POST to
   Meta's Graph API. Splits long messages at WhatsApp's 4096-char limit.
3. `validate_token(access_token, phone_number_id)` — GETs the phone
   number's metadata for the project edit page's "Test Connection"
   button. Returns `{display_name, verified_name, quality_rating, ok}`.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Pin the Graph API version so behaviour is stable as Meta releases new
# ones. Bump only after re-testing send + validate flows.
_GRAPH_API_VERSION = "v21.0"
_GRAPH_BASE = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"

_WHATSAPP_MAX_MESSAGE_LEN = 4096


def verify_signature(raw_body: bytes, sig_header: Optional[str], app_secret: str) -> bool:
    """Constant-time HMAC-SHA256 verification of the X-Hub-Signature-256
    header that Meta attaches to every inbound webhook POST. Returns
    False on any failure mode (missing header, malformed prefix, mismatch)
    so callers can treat any falsy as "reject"."""
    if not sig_header or not app_secret:
        return False
    # Meta's format is `sha256=<hexdigest>`.
    if not sig_header.startswith("sha256="):
        return False
    provided = sig_header[len("sha256="):]
    try:
        expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    except Exception:
        return False
    return hmac.compare_digest(provided, expected)


def send_message(access_token: str, phone_number_id: str, to: str, text: str) -> dict:
    """Send a free-form text message. Returns the Meta API response on
    success; raises on HTTP errors so callers can surface the failure
    (e.g. 24h-window violations). Splits at the 4096-char limit and
    sends each chunk as a separate message — same as our Telegram client."""
    if not access_token or not phone_number_id:
        raise ValueError("access_token and phone_number_id are required")
    if to is None or to == "":
        raise ValueError("recipient `to` is required")
    if text is None:
        text = ""
    # Strip a leading '+' if the admin pasted one — Meta wants bare digits.
    to = str(to).lstrip("+")

    chunks = (
        [text[i:i + _WHATSAPP_MAX_MESSAGE_LEN] for i in range(0, len(text), _WHATSAPP_MAX_MESSAGE_LEN)]
        if text
        else [""]
    )
    last = None
    url = f"{_GRAPH_BASE}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    for chunk in chunks:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": chunk},
        }
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        if resp.status_code >= 400:
            # Surface Meta's error message verbatim — usually self-explanatory
            # ("Free-form messages outside the 24h window are not supported", etc.)
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            raise RuntimeError(f"WhatsApp send failed (HTTP {resp.status_code}): {detail}")
        last = resp.json()
    return last or {}


def validate_token(access_token: str, phone_number_id: str) -> dict:
    """Probe Meta's API to confirm the credentials work without sending
    a real message. Returns ``{ok, display_name, verified_name,
    quality_rating}`` on success and ``{ok: False, error: <str>}`` on
    failure — never raises, so the admin's Test Connection button can
    show a friendly message either way."""
    if not access_token or not phone_number_id:
        return {"ok": False, "error": "access_token and phone_number_id are required"}
    url = f"{_GRAPH_BASE}/{phone_number_id}"
    params = {"fields": "display_phone_number,verified_name,quality_rating,name_status"}
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
    except Exception as e:
        return {"ok": False, "error": f"network error: {e}"}
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
            msg = err.get("message") or resp.text
        except Exception:
            msg = resp.text
        return {"ok": False, "error": f"HTTP {resp.status_code}: {msg}"}
    data = resp.json() or {}
    return {
        "ok": True,
        "display_name": data.get("display_phone_number"),
        "verified_name": data.get("verified_name"),
        "quality_rating": data.get("quality_rating"),
        "name_status": data.get("name_status"),
    }
