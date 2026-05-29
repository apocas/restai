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

@router.get("/projects/{projectID}/comments", tags=["Comments"])
async def list_project_comments(
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all comments for a project (newest first)."""
    from restai.models.databasemodels import ProjectCommentDatabase
    from restai.models.models import ProjectCommentResponse

    comments = (
        db_wrapper.db.query(ProjectCommentDatabase)
        .filter(ProjectCommentDatabase.project_id == projectID)
        .order_by(ProjectCommentDatabase.created_at.desc())
        .all()
    )
    return [
        ProjectCommentResponse(
            id=c.id,
            project_id=c.project_id,
            username=c.user.username if c.user else "unknown",
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in comments
    ]


@router.post("/projects/{projectID}/comments", status_code=201, tags=["Comments"])
async def create_project_comment(
    projectID: int = PathParam(description="Project ID"),
    body: ProjectCommentCreate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Add a comment to a project."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectCommentDatabase
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    comment = ProjectCommentDatabase(
        project_id=projectID,
        user_id=user.id,
        content=body.content,
        created_at=now,
        updated_at=now,
    )
    db_wrapper.db.add(comment)
    db_wrapper.db.commit()
    db_wrapper.db.refresh(comment)
    return {"id": comment.id, "message": "Comment added."}


@router.patch("/projects/{projectID}/comments/{commentID}", tags=["Comments"])
async def update_project_comment(
    projectID: int = PathParam(description="Project ID"),
    commentID: int = PathParam(description="Comment ID"),
    body: ProjectCommentUpdate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Edit a comment (owner or admin only)."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectCommentDatabase
    from datetime import datetime, timezone

    comment = db_wrapper.db.query(ProjectCommentDatabase).filter(
        ProjectCommentDatabase.id == commentID,
        ProjectCommentDatabase.project_id == projectID,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")

    comment.content = body.content
    comment.updated_at = datetime.now(timezone.utc)
    db_wrapper.db.commit()
    return {"message": "Comment updated."}


@router.delete("/projects/{projectID}/comments/{commentID}", tags=["Comments"])
async def delete_project_comment(
    projectID: int = PathParam(description="Project ID"),
    commentID: int = PathParam(description="Comment ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a comment (owner or admin only)."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectCommentDatabase

    comment = db_wrapper.db.query(ProjectCommentDatabase).filter(
        ProjectCommentDatabase.id == commentID,
        ProjectCommentDatabase.project_id == projectID,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Can only delete your own comments")

    db_wrapper.db.delete(comment)
    db_wrapper.db.commit()
    return {"message": "Comment deleted."}

