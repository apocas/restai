"""Shared OpenAI credential lookup for the DALL-E 3 and gpt-image-1.5 generators.

Reads `openai_api_key` from the platform settings table (encrypted at rest,
transparently decrypted by the DB wrapper). Falls back to the `OPENAI_API_KEY`
environment variable so existing deployments keep working until an admin
pastes the key into the admin Settings page.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from restai.database import get_db_wrapper


def get_openai_api_key() -> str:
    """Return the configured OpenAI API key. Raises HTTP 400 when missing so
    the image endpoint surfaces a clear admin-facing error instead of a
    generic 500."""
    db = get_db_wrapper()
    try:
        key = (db.get_setting_value("openai_api_key", "") or "").strip()
    finally:
        db.db.close()
    if not key:
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail=(
                "OpenAI API key is not configured. Set it in Settings \u2192 OpenAI "
                "(or via the OPENAI_API_KEY environment variable)."
            ),
        )
    return key


def has_openai_api_key(db_wrapper) -> bool:
    """Non-raising variant used by the /image list endpoint to decide whether
    to surface OpenAI-backed generators. Accepts an existing DBWrapper so the
    caller can reuse its session."""
    try:
        key = (db_wrapper.get_setting_value("openai_api_key", "") or "").strip()
    except Exception:
        key = ""
    if key:
        return True
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())
