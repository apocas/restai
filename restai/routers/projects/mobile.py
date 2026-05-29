import base64
import json
import logging
from typing import Optional
import os
import re
import traceback
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Path as PathParam,
    Request,
    UploadFile,
    BackgroundTasks,
    Query,
)
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from unidecode import unidecode
from restai import config
from restai.auth import (
    get_current_username,
    get_current_username_project,
    get_current_username_project_public,
    check_not_restricted,
    check_user_can_use_mcp_host,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.helper import chat_main
from restai.loaders.url import SeleniumWebReader
from restai.models.models import (
    FindModel,
    IngestResponse,
    ProjectModel,
    ProjectModelCreate,
    ProjectModelUpdate,
    ProjectResponse,
    ProjectsResponse,
    ProjectCommentCreate,
    ProjectCommentUpdate,
    ChatModel,
    TextIngestModel,
    URLIngestModel,
    User,
    WidgetCreate,
    WidgetUpdate,
    WidgetConfig,
    WidgetResponse,
    WidgetCreatedResponse,
    BlockGenerateRequest,
    SystemPromptGenerateRequest,
    ProjectToolUpdate,
    RoutineCreate,
    RoutineUpdate,
    validate_safe_name,
)
import uuid
import secrets
from restai.utils.crypto import encrypt_api_key, hash_api_key, encrypt_field
from restai.brain import Brain
from restai.project import Project
from restai.vectordb import tools
from restai.integrations.knowledge_graph import extract_and_persist_safe
from restai.vectordb.tools import (
    find_file_loader,
    extract_keywords_for_metadata,
    index_documents_classic,
    index_documents_docling,
)
from restai.models.databasemodels import OutputDatabase, ProjectDatabase, ProjectInvitationDatabase
from restai.settings import mask_key
import datetime
from sqlalchemy import func, Integer, case
import calendar
import tempfile
import shutil

from restai.routers.projects._common import (
    router,
    get_project,
    _mask_sync_sources,
    _SENSITIVE_OPTION_KEYS,
)

def _mobile_default_host(request: Request) -> str:
    """Resolve the host URL mobile apps should hit."""
    configured = getattr(config, "RESTAI_URL", None)
    if configured:
        return str(configured).rstrip("/")
    try:
        return f"{request.url.scheme}://{request.url.netloc}"
    except Exception:
        return ""


def _mobile_key_description(project_name: str) -> str:
    return f"RESTai Mobile — project {project_name}"


def _mobile_status_payload(request: Request, project_db, api_key_row, api_key_plaintext: Optional[str] = None) -> dict:
    """Shape GET/POST response; surfaces plaintext key while enabled (for QR)."""
    enabled = api_key_row is not None
    payload = {
        "enabled": enabled,
        "key_prefix": api_key_row.key_prefix if api_key_row else None,
        "host": _mobile_default_host(request),
    }
    if enabled:
        plaintext = api_key_plaintext
        if plaintext is None:
            try:
                from restai.utils.crypto import decrypt_api_key
                plaintext = decrypt_api_key(api_key_row.encrypted_key)
            except Exception:
                plaintext = None
        if plaintext:
            payload["qr"] = {
                "host": payload["host"],
                "project_id": project_db.id,
                "project_name": project_db.name,
                "api_key": plaintext,
            }
    return payload


def _get_mobile_api_key(db_wrapper: DBWrapper, project_db):
    """Return the ApiKeyDatabase row paired with this project's Mobile integration."""
    opts = json.loads(project_db.options) if project_db.options else {}
    key_id = opts.get("mobile_api_key_id")
    if not key_id:
        return None
    from restai.models.databasemodels import ApiKeyDatabase
    row = db_wrapper.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == int(key_id)).first()
    return row


def _persist_mobile_key(db_wrapper: DBWrapper, project_db, api_key_id):
    """Store (or clear) the mobile api key id on the project's options blob."""
    opts = json.loads(project_db.options) if project_db.options else {}
    if api_key_id is None:
        opts.pop("mobile_api_key_id", None)
        opts["mobile_enabled"] = False
    else:
        opts["mobile_api_key_id"] = int(api_key_id)
        opts["mobile_enabled"] = True
    project_db.options = json.dumps(opts)
    db_wrapper.db.commit()


def _mint_mobile_api_key(db_wrapper: DBWrapper, user, project_db) -> tuple:
    """Create a read-only project-scoped API key; returns (row, plaintext)."""
    import uuid as _uuid
    import secrets as _secrets
    from restai.utils.crypto import encrypt_api_key, hash_api_key

    plaintext = _uuid.uuid4().hex + _secrets.token_urlsafe(32)
    encrypted = encrypt_api_key(plaintext)
    key_hash = hash_api_key(plaintext)
    key_prefix = plaintext[:8]

    api_key_row = db_wrapper.create_api_key(
        user_id=user.id,
        encrypted_key=encrypted,
        key_hash=key_hash,
        key_prefix=key_prefix,
        description=_mobile_key_description(project_db.name),
        allowed_projects=json.dumps([project_db.id]),
        read_only=True,
    )
    return api_key_row, plaintext


@router.get("/projects/{projectID}/mobile", tags=["Mobile"])
async def mobile_status(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return Mobile integration status (plaintext only at enable/regenerate time)."""
    project_db = db_wrapper.get_project_by_id(projectID)
    if project_db is None:
        raise HTTPException(status_code=404, detail="Project not found")
    row = _get_mobile_api_key(db_wrapper, project_db)
    return _mobile_status_payload(request, project_db, row)


@router.post("/projects/{projectID}/mobile/enable", tags=["Mobile"])
async def mobile_enable(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Turn Mobile integration ON; idempotent (no re-exposure of existing key)."""
    check_not_restricted(user)
    project_db = db_wrapper.get_project_by_id(projectID)
    if project_db is None:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = _get_mobile_api_key(db_wrapper, project_db)
    if existing is not None:
        return _mobile_status_payload(request, project_db, existing)

    api_key_row, plaintext = _mint_mobile_api_key(db_wrapper, user, project_db)
    _persist_mobile_key(db_wrapper, project_db, api_key_row.id)
    return _mobile_status_payload(request, project_db, api_key_row, api_key_plaintext=plaintext)


@router.post("/projects/{projectID}/mobile/disable", tags=["Mobile"])
async def mobile_disable(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Turn Mobile integration OFF; revokes the key (all paired phones lose access)."""
    check_not_restricted(user)
    project_db = db_wrapper.get_project_by_id(projectID)
    if project_db is None:
        raise HTTPException(status_code=404, detail="Project not found")

    row = _get_mobile_api_key(db_wrapper, project_db)
    if row is not None:
        db_wrapper.db.delete(row)
        db_wrapper.db.commit()
    _persist_mobile_key(db_wrapper, project_db, None)
    return _mobile_status_payload(request, project_db, None)


@router.post("/projects/{projectID}/mobile/regenerate", tags=["Mobile"])
async def mobile_regenerate(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Invalidate paired phones and mint a fresh key."""
    check_not_restricted(user)
    project_db = db_wrapper.get_project_by_id(projectID)
    if project_db is None:
        raise HTTPException(status_code=404, detail="Project not found")

    old = _get_mobile_api_key(db_wrapper, project_db)
    if old is not None:
        db_wrapper.db.delete(old)
        db_wrapper.db.commit()

    api_key_row, plaintext = _mint_mobile_api_key(db_wrapper, user, project_db)
    _persist_mobile_key(db_wrapper, project_db, api_key_row.id)
    return _mobile_status_payload(request, project_db, api_key_row, api_key_plaintext=plaintext)
