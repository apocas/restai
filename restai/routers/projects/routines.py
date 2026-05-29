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

# ── Project Routines (scheduled messages) ────────────────────────────────


@router.get("/projects/{projectID}/routines", tags=["Routines"])
async def list_routines(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all routines for a project."""
    routines = db_wrapper.get_project_routines(projectID)
    return {
        "routines": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "name": r.name,
                "message": r.message,
                "schedule_minutes": r.schedule_minutes,
                "enabled": bool(r.enabled),
                "last_run": r.last_run.isoformat() if r.last_run else None,
                "last_result": r.last_result,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in routines
        ]
    }


@router.post("/projects/{projectID}/routines", tags=["Routines"], status_code=201)
async def create_routine(
    body: RoutineCreate,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new routine for a project."""
    check_not_restricted(user)
    routine = db_wrapper.create_project_routine(
        project_id=projectID,
        name=body.name,
        message=body.message,
        schedule_minutes=body.schedule_minutes,
        enabled=body.enabled,
    )
    return {
        "id": routine.id,
        "name": routine.name,
        "message": routine.message,
        "schedule_minutes": routine.schedule_minutes,
        "enabled": bool(routine.enabled),
    }


@router.patch("/projects/{projectID}/routines/{routineID}", tags=["Routines"])
async def update_routine(
    body: RoutineUpdate,
    projectID: int = PathParam(description="Project ID"),
    routineID: int = PathParam(description="Routine ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update a routine."""
    check_not_restricted(user)
    routine = db_wrapper.get_project_routine_by_id(routineID)
    if not routine or routine.project_id != projectID:
        raise HTTPException(status_code=404, detail="Routine not found")

    from datetime import datetime, timezone
    if body.name is not None:
        routine.name = body.name
    if body.message is not None:
        routine.message = body.message
    if body.schedule_minutes is not None:
        routine.schedule_minutes = body.schedule_minutes
    if body.enabled is not None:
        routine.enabled = body.enabled
    routine.updated_at = datetime.now(timezone.utc)
    db_wrapper.db.commit()

    return {
        "id": routine.id,
        "name": routine.name,
        "message": routine.message,
        "schedule_minutes": routine.schedule_minutes,
        "enabled": bool(routine.enabled),
    }


@router.delete("/projects/{projectID}/routines/{routineID}", tags=["Routines"], status_code=204)
async def delete_routine(
    projectID: int = PathParam(description="Project ID"),
    routineID: int = PathParam(description="Routine ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a routine."""
    check_not_restricted(user)
    routine = db_wrapper.get_project_routine_by_id(routineID)
    if not routine or routine.project_id != projectID:
        raise HTTPException(status_code=404, detail="Routine not found")
    db_wrapper.delete_project_routine(routineID)


@router.post("/projects/{projectID}/routines/{routineID}/fire", tags=["Routines"])
async def fire_routine(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    routineID: int = PathParam(description="Routine ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Manually trigger a routine. Runs the message through the project and returns the result."""
    routine = db_wrapper.get_project_routine_by_id(routineID)
    if not routine or routine.project_id != projectID:
        raise HTTPException(status_code=404, detail="Routine not found")

    brain = request.app.state.brain
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    from fastapi import BackgroundTasks
    import inspect

    q = ChatModel(question=routine.message)
    background_tasks = BackgroundTasks()

    result = await chat_main(
        request, brain, project, q, user, db_wrapper, background_tasks,
    )

    for task in background_tasks.tasks:
        try:
            if inspect.iscoroutinefunction(task.func):
                await task.func(*task.args, **task.kwargs)
            else:
                task.func(*task.args, **task.kwargs)
        except Exception:
            pass

    from datetime import datetime, timezone
    answer = result.get("answer", "") if isinstance(result, dict) else str(result)
    routine.last_run = datetime.now(timezone.utc)
    routine.last_result = answer[:2000] if answer else None
    routine.updated_at = datetime.now(timezone.utc)
    db_wrapper.db.commit()

    # Manual-fire row in the execution log; `manual=True` distinguishes from cron.
    try:
        from restai.models.databasemodels import RoutineExecutionLogDatabase
        db_wrapper.db.add(RoutineExecutionLogDatabase(
            routine_id=routine.id, project_id=routine.project_id,
            status="ok", result=(answer[:2000] if answer else None),
            duration_ms=None, is_manual=True,
            created_at=datetime.now(timezone.utc),
        ))
        db_wrapper.db.commit()
    except Exception:
        logging.exception("Failed to write routine execution log row for manual fire")

    return result


@router.get("/projects/{projectID}/routines/{routineID}/history", tags=["Routines"])
async def get_routine_history(
    projectID: int = PathParam(description="Project ID"),
    routineID: int = PathParam(description="Routine ID"),
    limit: int = Query(50, ge=1, le=500),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Recent execution history for a routine, newest first."""
    from restai.models.databasemodels import RoutineExecutionLogDatabase
    routine = db_wrapper.get_project_routine_by_id(routineID)
    if not routine or routine.project_id != projectID:
        raise HTTPException(status_code=404, detail="Routine not found")
    rows = (
        db_wrapper.db.query(RoutineExecutionLogDatabase)
        .filter(RoutineExecutionLogDatabase.routine_id == routineID)
        .order_by(RoutineExecutionLogDatabase.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "result": r.result,
                "duration_ms": r.duration_ms,
                "manual": bool(r.is_manual),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }

