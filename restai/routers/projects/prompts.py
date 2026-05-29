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

@router.get("/projects/{projectID}/prompts", tags=["Projects"])
async def list_prompt_versions(
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all prompt versions for a project."""
    from restai.models.models import PromptVersionResponse
    versions = db_wrapper.get_prompt_versions(projectID)
    return [PromptVersionResponse.model_validate(v) for v in versions]


@router.get("/projects/{projectID}/prompts/{versionID}", tags=["Projects"])
async def get_prompt_version(
    projectID: int = PathParam(description="Project ID"),
    versionID: int = PathParam(description="Prompt version ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get a specific prompt version."""
    from restai.models.models import PromptVersionResponse
    version = db_wrapper.get_prompt_version(versionID)
    if version is None or version.project_id != projectID:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return PromptVersionResponse.model_validate(version)


@router.post("/projects/{projectID}/prompts/{versionID}/activate", tags=["Projects"])
async def activate_prompt_version(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    versionID: int = PathParam(description="Prompt version ID to activate"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Restore a previous prompt version as the active system prompt."""
    check_not_restricted(user)
    version = db_wrapper.get_prompt_version(versionID)
    if version is None or version.project_id != projectID:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    project = db_wrapper.get_project_by_id(projectID)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    from restai.models.models import ProjectModelUpdate
    update = ProjectModelUpdate(system=version.system_prompt)
    update._user_id = user.id
    db_wrapper.edit_project(projectID, update)

    return {"project": projectID, "activated_version": version.version}

