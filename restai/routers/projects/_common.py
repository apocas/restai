import logging
from fastapi import (
    APIRouter,
    HTTPException,
)
from restai import config
from restai.database import DBWrapper
from restai.utils.crypto import PROJECT_SENSITIVE_KEYS
from restai.brain import Brain
from restai.settings import mask_key

# Mask EVERY secret in the project options blob on read (GET / list) and
# preserve-on-mask on edit. Kept aligned with the at-rest encryption set so
# decrypted secrets (whatsapp/twilio/webhook tokens, etc.) never leave the
# server in an API response. Previously only 4 of the 9 keys were masked,
# leaking whatsapp_access_token / whatsapp_app_secret / whatsapp_verify_token /
# twilio_auth_token / webhook_secret in plaintext to any project member.
_SENSITIVE_OPTION_KEYS = tuple(sorted(PROJECT_SENSITIVE_KEYS))

def _mask_sync_sources(options: dict):
    """Mask sensitive credentials inside sync_sources list."""
    sources = options.get("sync_sources")
    if not sources or not isinstance(sources, list):
        return
    for src in sources:
        if isinstance(src, dict):
            for key in ("s3_access_key", "s3_secret_key", "confluence_api_token", "sharepoint_client_secret", "gdrive_service_account_json"):
                val = src.get(key)
                if val:
                    src[key] = mask_key(val)

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


def get_project(projectID: int, db_wrapper: DBWrapper, brain: Brain):
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
