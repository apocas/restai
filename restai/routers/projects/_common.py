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
    """Mask sensitive credentials nested inside the options blob.

    Covers `sync_sources[]` and `mcp_servers[]`. The latter was unmasked, so an
    MCP server's `env` / `headers` — which is exactly where a third-party
    bearer token or API key is configured — came back in plaintext to every
    project member on a plain project GET.
    """
    sources = options.get("sync_sources")
    if sources and isinstance(sources, list):
        for src in sources:
            if isinstance(src, dict):
                for key in ("s3_access_key", "s3_secret_key", "confluence_api_token", "sharepoint_client_secret", "gdrive_service_account_json"):
                    val = src.get(key)
                    if val:
                        src[key] = mask_key(val)

    servers = options.get("mcp_servers")
    if servers and isinstance(servers, list):
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            # Every value in these maps is credential-shaped by construction.
            for bag in ("env", "headers"):
                values = srv.get(bag)
                if isinstance(values, dict):
                    for k, v in list(values.items()):
                        if v and isinstance(v, str):
                            values[k] = mask_key(v)

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


def get_project(projectID: int, db_wrapper: DBWrapper, brain: Brain):
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
