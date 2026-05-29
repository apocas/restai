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

@router.post("/projects/{projectID}/widgets", status_code=201, tags=["Widgets"])
async def create_widget(
    projectID: int = PathParam(description="Project ID"),
    body: WidgetCreate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new widget for a project. Returns the widget key once."""
    check_not_restricted(user)

    plaintext_key = "wk_" + uuid.uuid4().hex + secrets.token_urlsafe(32)
    encrypted = encrypt_api_key(plaintext_key)
    key_hash = hash_api_key(plaintext_key)
    key_prefix = plaintext_key[:11]

    widget = db_wrapper.create_widget(
        project_id=projectID,
        creator_id=user.id,
        encrypted_key=encrypted,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        config_json=body.config.model_dump_json(),
        allowed_domains_json=json.dumps(body.allowed_domains),
    )

    return WidgetCreatedResponse(
        id=widget.id,
        project_id=widget.project_id,
        name=widget.name,
        config=body.config,
        allowed_domains=body.allowed_domains,
        enabled=widget.enabled,
        key_prefix=widget.key_prefix,
        created_at=widget.created_at,
        updated_at=widget.updated_at,
        widget_key=plaintext_key,
    )


@router.get("/projects/{projectID}/widgets", tags=["Widgets"])
async def list_widgets(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all widgets for a project."""
    widgets = db_wrapper.get_widgets_for_project(projectID)
    return {"widgets": [WidgetResponse.model_validate(w).model_dump() for w in widgets]}


@router.get("/projects/{projectID}/widgets/{widgetID}", tags=["Widgets"])
async def get_widget(
    projectID: int = PathParam(description="Project ID"),
    widgetID: int = PathParam(description="Widget ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get widget details."""
    widget = db_wrapper.get_widget_by_id(widgetID)
    if widget is None or widget.project_id != projectID:
        raise HTTPException(status_code=404, detail="Widget not found")
    return WidgetResponse.model_validate(widget)


@router.patch("/projects/{projectID}/widgets/{widgetID}", tags=["Widgets"])
async def update_widget(
    projectID: int = PathParam(description="Project ID"),
    widgetID: int = PathParam(description="Widget ID"),
    body: WidgetUpdate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update widget configuration."""
    check_not_restricted(user)

    widget = db_wrapper.get_widget_by_id(widgetID)
    if widget is None or widget.project_id != projectID:
        raise HTTPException(status_code=404, detail="Widget not found")

    if body.name is not None:
        widget.name = body.name
    if body.config is not None:
        widget.config = body.config.model_dump_json()
    if body.allowed_domains is not None:
        widget.allowed_domains = json.dumps(body.allowed_domains)
    if body.enabled is not None:
        widget.enabled = body.enabled

    widget.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db_wrapper.db.commit()

    return WidgetResponse.model_validate(widget)


@router.delete("/projects/{projectID}/widgets/{widgetID}", status_code=204, tags=["Widgets"])
async def delete_widget(
    projectID: int = PathParam(description="Project ID"),
    widgetID: int = PathParam(description="Widget ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a widget."""
    check_not_restricted(user)
    widget = db_wrapper.get_widget_by_id(widgetID)
    if widget is None or widget.project_id != projectID:
        raise HTTPException(status_code=404, detail="Widget not found")
    db_wrapper.delete_widget(widget)


@router.post("/projects/{projectID}/widgets/{widgetID}/regenerate-key", tags=["Widgets"])
async def regenerate_widget_key(
    projectID: int = PathParam(description="Project ID"),
    widgetID: int = PathParam(description="Widget ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Regenerate widget key. Returns the new key once."""
    check_not_restricted(user)

    widget = db_wrapper.get_widget_by_id(widgetID)
    if widget is None or widget.project_id != projectID:
        raise HTTPException(status_code=404, detail="Widget not found")

    plaintext_key = "wk_" + uuid.uuid4().hex + secrets.token_urlsafe(32)
    widget.encrypted_key = encrypt_api_key(plaintext_key)
    widget.key_hash = hash_api_key(plaintext_key)
    widget.key_prefix = plaintext_key[:11]
    widget.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db_wrapper.db.commit()

    resp = WidgetResponse.model_validate(widget).model_dump()
    resp["widget_key"] = plaintext_key
    return resp


@router.post("/projects/{projectID}/widgets/{widgetID}/context-secret", tags=["Widgets"])
async def generate_widget_context_secret(
    projectID: int = PathParam(description="Project ID"),
    widgetID: int = PathParam(description="Widget ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Generate a context secret for signed widget context injection. Returns the secret once."""
    check_not_restricted(user)

    widget = db_wrapper.get_widget_by_id(widgetID)
    if widget is None or widget.project_id != projectID:
        raise HTTPException(status_code=404, detail="Widget not found")

    plaintext_secret = secrets.token_urlsafe(32)
    widget.context_secret = encrypt_field(plaintext_secret)
    widget.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db_wrapper.db.commit()

    return {"context_secret": plaintext_secret}


@router.delete("/projects/{projectID}/widgets/{widgetID}/context-secret", tags=["Widgets"])
async def remove_widget_context_secret(
    projectID: int = PathParam(description="Project ID"),
    widgetID: int = PathParam(description="Widget ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Remove the context secret, disabling signed context for this widget."""
    check_not_restricted(user)

    widget = db_wrapper.get_widget_by_id(widgetID)
    if widget is None or widget.project_id != projectID:
        raise HTTPException(status_code=404, detail="Widget not found")

    widget.context_secret = None
    widget.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db_wrapper.db.commit()

    return {"detail": "Context secret removed"}

