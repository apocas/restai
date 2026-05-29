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

@router.get("/projects/{projectID}/custom-tools", tags=["Projects"])
async def list_project_custom_tools(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List agent-created tools for a project."""
    tools = db_wrapper.get_project_tools(projectID)
    return {
        "tools": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "code": t.code,
                "enabled": bool(t.enabled),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tools
        ]
    }


@router.patch("/projects/{projectID}/custom-tools/{toolName}", tags=["Projects"])
async def toggle_project_custom_tool(
    projectID: int = PathParam(description="Project ID"),
    toolName: str = PathParam(description="Tool name"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Toggle an agent-created tool on or off."""
    check_not_restricted(user)
    tool = db_wrapper.get_project_tool_by_name(projectID, toolName)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    from datetime import datetime, timezone
    tool.enabled = not tool.enabled
    tool.updated_at = datetime.now(timezone.utc)
    db_wrapper.db.commit()
    return {"name": tool.name, "enabled": bool(tool.enabled)}


@router.put("/projects/{projectID}/custom-tools/{toolName}", tags=["Projects"])
async def update_project_custom_tool(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    toolName: str = PathParam(description="Tool name"),
    body: ProjectToolUpdate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update an agent-created tool's description, parameters, or code."""
    check_not_restricted(user)
    tool = db_wrapper.get_project_tool_by_name(projectID, toolName)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    final_description = body.description if body.description is not None else tool.description
    final_parameters = body.parameters if body.parameters is not None else tool.parameters
    final_code = body.code if body.code is not None else tool.code

    if not final_description or not final_description.strip():
        raise HTTPException(status_code=400, detail="Description is required.")
    if not final_code or not final_code.strip():
        raise HTTPException(status_code=400, detail="Code is required.")

    try:
        params_dict = json.loads(final_parameters) if isinstance(final_parameters, str) else final_parameters
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters JSON: {e}")

    brain = request.app.state.brain
    warning = None
    if getattr(brain, "docker_manager", None):
        script = f"import json, sys\nargs = json.loads(sys.stdin.readline() or '{{}}')\n{final_code}"
        test_result = brain.docker_manager.run_script("ephemeral", script, stdin_data="{}")
        if test_result.startswith("ERROR:"):
            raise HTTPException(status_code=400, detail=f"Code validation failed — {test_result}")
    else:
        warning = "Docker is not configured; code was saved without sandbox validation."

    final_params_str = json.dumps(params_dict) if isinstance(params_dict, dict) else final_parameters
    db_wrapper.upsert_project_tool(
        project_id=projectID,
        name=toolName,
        description=final_description,
        parameters=final_params_str,
        code=final_code,
    )

    updated = db_wrapper.get_project_tool_by_name(projectID, toolName)
    result = {
        "id": updated.id,
        "name": updated.name,
        "description": updated.description,
        "parameters": updated.parameters,
        "code": updated.code,
        "enabled": bool(updated.enabled),
        "created_at": updated.created_at.isoformat() if updated.created_at else None,
        "updated_at": updated.updated_at.isoformat() if updated.updated_at else None,
    }
    if warning:
        result["warning"] = warning
    return result


@router.delete("/projects/{projectID}/custom-tools/{toolName}", tags=["Projects"])
async def delete_project_custom_tool(
    projectID: int = PathParam(description="Project ID"),
    toolName: str = PathParam(description="Tool name"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an agent-created tool from a project."""
    check_not_restricted(user)
    if not db_wrapper.delete_project_tool(projectID, toolName):
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"detail": f"Tool '{toolName}' deleted"}


@router.post("/projects/{projectID}/block/generate", tags=["Projects"])
async def block_generate_workspace(
    request: Request,
    body: BlockGenerateRequest,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Use the system LLM to generate a Blockly workspace from a plain-English description."""
    check_not_restricted(user)

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "block":
        raise HTTPException(status_code=400, detail="Only block projects support workspace generation.")

    # Names of projects the user can call (for valid restai_call_project blocks).
    all_projects = db_wrapper.db.query(ProjectDatabase).all()
    available_projects = [
        p.name for p in all_projects
        if p.id != projectID and (user.is_admin or p.id in user.get_project_ids())
    ]

    from restai.utils.blockly_ai import generate_workspace_from_description
    try:
        workspace = await generate_workspace_from_description(
            request.app.state.brain, db_wrapper, body.description, available_projects,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"workspace": workspace}


@router.post("/projects/{projectID}/system-prompt/generate", tags=["Projects"])
async def generate_system_prompt_endpoint(
    request: Request,
    body: SystemPromptGenerateRequest,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Use the system LLM to draft a system prompt from a short description."""
    check_not_restricted(user)

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    project_type = body.project_type or project.props.type

    from restai.utils.prompt_ai import generate_system_prompt
    try:
        text = await generate_system_prompt(
            request.app.state.brain, db_wrapper, body.description, project_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"system_prompt": text}

