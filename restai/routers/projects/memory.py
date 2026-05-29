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

@router.get("/projects/{projectID}/memory-bank", tags=["Memory Bank"])
async def list_memory_bank(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Visualizer payload: entries grouped by granularity + aggregate stats."""
    from restai.models.databasemodels import ProjectMemoryBankEntryDatabase
    project = db_wrapper.get_project_by_id(projectID)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    options = json.loads(project.options) if project.options else {}
    enabled = bool(options.get("memory_bank_enabled"))
    max_tokens = int(options.get("memory_bank_max_tokens") or 2000)

    rows = (
        db_wrapper.db.query(ProjectMemoryBankEntryDatabase)
        .filter(ProjectMemoryBankEntryDatabase.project_id == projectID)
        .all()
    )

    def _row(r):
        return {
            "id": r.id,
            "chat_id": r.chat_id,
            "granularity": r.granularity,
            "period_key": r.period_key,
            "summary": r.summary or "",
            "token_count": r.token_count or 0,
            "source_message_count": r.source_message_count or 0,
            "last_source_at": r.last_source_at.isoformat() if r.last_source_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

    entries = [_row(r) for r in rows]
    entries.sort(
        key=lambda e: e["last_source_at"] or e["updated_at"] or e["created_at"] or "",
        reverse=True,
    )
    counts = {"conversation": 0, "day": 0, "week": 0, "month": 0}
    for r in rows:
        counts[r.granularity] = counts.get(r.granularity, 0) + 1
    total_tokens = sum((r.token_count or 0) for r in rows)

    return {
        "enabled": enabled,
        "max_tokens": max_tokens,
        "total_tokens": total_tokens,
        "entry_count": len(rows),
        "counts_by_granularity": counts,
        "entries": entries,
    }


@router.get("/projects/{projectID}/memory-bank/preview", tags=["Memory Bank"])
async def preview_memory_bank(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the exact text block prepended to the system prompt this turn."""
    project = db_wrapper.get_project_by_id(projectID)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    options = json.loads(project.options) if project.options else {}
    max_tokens = int(options.get("memory_bank_max_tokens") or 2000)
    from restai.memory import bank as memory_bank
    block = memory_bank.render_for_prompt(db_wrapper, projectID, max_tokens)
    from restai.tools import tokens_from_string
    return {
        "block": block,
        "tokens": tokens_from_string(block) if block else 0,
        "max_tokens": max_tokens,
    }


@router.post("/projects/{projectID}/memory-search", tags=["Memory Search"])
async def memory_search_query(
    request: Request,
    body: dict,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Run the agent's `search_memories` tool and return its raw text result."""
    project = db_wrapper.get_project_by_id(projectID)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    try:
        k = int(body.get("k") or 5)
    except Exception:
        k = 5

    from restai.llms.tools.search_memories import search_memories
    brain = request.app.state.brain
    result = search_memories(
        query=query,
        k=k,
        _brain=brain,
        _project_id=projectID,
    )
    return {"result": result}


@router.post("/projects/{projectID}/memory-bank/clear", tags=["Memory Bank"])
async def clear_memory_bank(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Wipe every entry for this project. Cron will re-summarize new
    conversations from `OutputDatabase` on the next tick."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectMemoryBankEntryDatabase
    deleted = (
        db_wrapper.db.query(ProjectMemoryBankEntryDatabase)
        .filter(ProjectMemoryBankEntryDatabase.project_id == projectID)
        .delete(synchronize_session=False)
    )
    db_wrapper.db.commit()
    return {"deleted": int(deleted or 0)}

