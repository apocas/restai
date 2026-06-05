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

@router.get("/projects", response_model=ProjectsResponse, tags=["Projects"])
async def route_get_projects(
    _: Request,
    v_filter: str = Query("", alias="filter", description="Filter mode: 'public' to list only public projects, empty for all accessible projects"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start offset"),
    end: int = Query(10000, ge=1, le=100000, description="Pagination end offset"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List projects accessible to the current user."""
    query = db_wrapper.db.query(ProjectDatabase)

    if v_filter == "public":
        user_team_ids = {t.id for t in (user.teams or [])} | {t.id for t in (user.admin_teams or [])}
        if user.is_admin:
            query = query.filter(ProjectDatabase.public == True)
        else:
            query = query.filter(
                ProjectDatabase.public == True,
                ProjectDatabase.team_id.in_(user_team_ids) if user_team_ids else False,
            )
    elif not user.is_admin:
        accessible_ids = user.get_project_ids()
        if user.admin_teams:
            admin_team_ids = {t.id for t in user.admin_teams}
            team_project_ids = {
                p[0] for p in db_wrapper.db.query(ProjectDatabase.id)
                .filter(ProjectDatabase.team_id.in_(admin_team_ids)).all()
            }
            accessible_ids = accessible_ids | team_project_ids
        query = query.filter(ProjectDatabase.id.in_(accessible_ids))

    if user.api_key_allowed_projects is not None:
        query = query.filter(ProjectDatabase.id.in_(user.api_key_allowed_projects))

    projects = query.offset(start).limit(end - start).all()

    serialized_projects = []
    for project in projects:
        project_model = ProjectModel.model_validate(project)
        project_model.creator_username = project.creator_user.username if project.creator_user else None

        project_dict = project_model.model_dump()

        if project_dict.get("team"):
            project_dict["team"] = {
                "id": project_dict["team"]["id"],
                "name": project_dict["team"]["name"],
            }

        if isinstance(project_dict.get("options"), dict):
            for key in _SENSITIVE_OPTION_KEYS:
                val = project_dict["options"].get(key)
                if val:
                    project_dict["options"][key] = mask_key(val)
            _mask_sync_sources(project_dict["options"])

        serialized_projects.append(project_dict)

    return {
        "projects": serialized_projects,
        "total": query.count(),
        "start": start,
        "end": end,
    }


@router.get("/projects/health", tags=["Projects"])
async def get_projects_health(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get health scores for all accessible projects."""
    import datetime as dt
    import json as _json
    from restai.models.databasemodels import GuardEventDatabase, EvalRunDatabase

    if user.is_admin:
        project_ids = [p.id for p in db_wrapper.db.query(ProjectDatabase.id).all()]
    else:
        project_ids = list(user.get_project_ids())

    if user.api_key_allowed_projects is not None:
        project_ids = [pid for pid in project_ids if pid in user.api_key_allowed_projects]

    if not project_ids:
        return []

    seven_days_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    thirty_days_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)

    activity_rows = (
        db_wrapper.db.query(
            OutputDatabase.project_id,
            func.count(OutputDatabase.id).label("requests"),
            func.avg(OutputDatabase.latency_ms).label("avg_latency"),
        )
        .filter(OutputDatabase.project_id.in_(project_ids), OutputDatabase.date >= seven_days_ago)
        .group_by(OutputDatabase.project_id)
        .all()
    )
    activity = {r.project_id: {"requests": r.requests, "avg_latency": r.avg_latency} for r in activity_rows}

    guard_rows = (
        db_wrapper.db.query(
            GuardEventDatabase.project_id,
            func.count(GuardEventDatabase.id).label("total"),
            func.sum(case((GuardEventDatabase.action == "block", 1), else_=0)).label("blocks"),
        )
        .filter(GuardEventDatabase.project_id.in_(project_ids), GuardEventDatabase.date >= thirty_days_ago)
        .group_by(GuardEventDatabase.project_id)
        .all()
    )
    guards = {r.project_id: {"total": r.total, "blocks": r.blocks or 0} for r in guard_rows}

    from sqlalchemy import desc
    eval_rows = (
        db_wrapper.db.query(EvalRunDatabase.project_id, EvalRunDatabase.summary)
        .filter(
            EvalRunDatabase.project_id.in_(project_ids),
            EvalRunDatabase.status == "completed",
            EvalRunDatabase.summary.isnot(None),
        )
        .order_by(EvalRunDatabase.completed_at.desc())
        .all()
    )
    evals = {}
    for r in eval_rows:
        if r.project_id not in evals and r.summary:
            try:
                summary = _json.loads(r.summary) if isinstance(r.summary, str) else r.summary
                scores = [v for v in summary.values() if isinstance(v, (int, float))]
                evals[r.project_id] = sum(scores) / len(scores) if scores else None
            except Exception:
                pass

    results = []
    for pid in project_ids:
        act = activity.get(pid, {})
        grd = guards.get(pid, {})
        eval_score = evals.get(pid)

        requests_7d = act.get("requests", 0)
        avg_latency = act.get("avg_latency")
        guard_total = grd.get("total", 0)
        guard_blocks = grd.get("blocks", 0)
        block_rate = guard_blocks / guard_total if guard_total > 0 else None

        if avg_latency is not None:
            if avg_latency < 500:
                latency_score = 1.0
            elif avg_latency < 2000:
                latency_score = 0.5
            else:
                latency_score = 0.0
        else:
            latency_score = 0.5

        if requests_7d > 10:
            activity_score = 1.0
        elif requests_7d > 0:
            activity_score = 0.5
        else:
            activity_score = 0.0

        if block_rate is not None:
            if block_rate < 0.05:
                guard_score = 1.0
            elif block_rate < 0.15:
                guard_score = 0.5
            else:
                guard_score = 0.0
        else:
            guard_score = 0.5

        if eval_score is not None:
            if eval_score > 0.8:
                eval_component = 1.0
            elif eval_score > 0.5:
                eval_component = 0.5
            else:
                eval_component = 0.0
        else:
            eval_component = 0.5

        health = round((latency_score * 30 + activity_score * 30 + guard_score * 20 + eval_component * 20))

        results.append({
            "project_id": pid,
            "health": health,
            "requests_7d": requests_7d,
            "avg_latency": round(avg_latency) if avg_latency else None,
            "guard_block_rate": round(block_rate, 3) if block_rate is not None else None,
            "eval_score": round(eval_score, 2) if eval_score is not None else None,
        })

    return results


@router.get("/projects/{projectID}", tags=["Projects"])
async def route_get_project(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get detailed information about a specific project."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        output = project.props.model_dump()
        final_output = {}

        try:
            llm_model = request.app.state.brain.get_llm(project.props.llm, db_wrapper)
        except Exception:
            llm_model = None

        final_output = output

        final_output["human_description"] = output["human_description"] or ""
        final_output["level"] = user.level
        final_output["users"] = [u["username"] for u in output["users"]]

        if project.props.team:
            final_output["team"] = {
                "id": project.props.team.id,
                "name": project.props.team.name,
            }

        match project.props.type:
            case "rag":
                if project.vector is not None:
                    chunks = project.vector.info()
                    if chunks is not None:
                        final_output["chunks"] = chunks
                else:
                    final_output["chunks"] = 0
                final_output["embeddings"] = output["embeddings"]
                final_output["vectorstore"] = output["vectorstore"]
                final_output["system"] = output["system"] or ""
            case "agent":
                final_output["system"] = output["system"] or ""
        if llm_model:
            final_output["llm_privacy"] = llm_model.props.privacy

        if isinstance(final_output.get("options"), dict):
            for key in _SENSITIVE_OPTION_KEYS:
                val = final_output["options"].get(key)
                if val:
                    final_output["options"][key] = mask_key(val)
            _mask_sync_sources(final_output["options"])

        del project

        return final_output
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/projects/{projectID}", tags=["Projects"])
async def route_delete_project(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a project and all associated data."""
    check_not_restricted(user)
    try:
        proj = get_project(projectID, db_wrapper, request.app.state.brain)

        if proj.props.options and proj.props.options.telegram_token:
            from restai.comms.telegram import stop_poller
            stop_poller(projectID)

        proj.delete()

        db_wrapper.db.query(OutputDatabase).filter(
            OutputDatabase.project_id == proj.props.id
        ).delete()

        db_wrapper.delete_project(db_wrapper.get_project_by_id(projectID))

        # Wipe app-builder source tree. Must stop the preview container FIRST
        # — it holds /var/www open via bind mount and racing the wipe empties public/.
        if proj.props.type == "app":
            from restai.app.storage import delete_project_root
            mgr = getattr(request.app.state.brain, "app_manager", None)
            if mgr is not None:
                try:
                    mgr.remove_container(projectID)
                except Exception:
                    logging.exception("Failed to stop app container before wipe (project=%s)", projectID)
            delete_project_root(projectID)

        return {"project": projectID}

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/projects/{projectID}", tags=["Projects"])
async def route_edit_project(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    projectModelUpdate: ProjectModelUpdate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update project configuration."""
    check_not_restricted(user)
    project = db_wrapper.get_project_by_id(projectID)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # search_knowledge target must be a RAG project the editing user can access
    # (the builtin re-checks per running user at call time; this is early UX feedback).
    skp = getattr(projectModelUpdate.options, "search_knowledge_project", None) if projectModelUpdate.options else None
    if skp:
        from restai.auth import user_can_access_project
        tgt = db_wrapper.get_project_by_name(skp)
        if tgt is None or tgt.type != "rag":
            raise HTTPException(status_code=400, detail="search_knowledge_project must be an existing RAG project")
        # Must live in the same team as this project (honour a team change in this PATCH).
        calling_team_id = getattr(projectModelUpdate, "team_id", None) or project.team_id
        if tgt.team_id is None or tgt.team_id != calling_team_id:
            raise HTTPException(status_code=400, detail=f"RAG project '{skp}' must be in the same team as this project")
        if not user_can_access_project(user, tgt.id, db_wrapper):
            raise HTTPException(status_code=403, detail=f"No access to RAG project '{skp}'")

    if (
        projectModelUpdate.llm
        and request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper) is None
    ):
        raise HTTPException(status_code=404, detail="LLM not found")

    if projectModelUpdate.llm and not projectModelUpdate.team_id:
        current_team = db_wrapper.get_team_by_id(project.team_id)
        if current_team:
            llm_model = request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper)
            if llm_model and llm_model.props.name not in [l.name for l in current_team.llms]:
                raise HTTPException(
                    status_code=403, detail=f"Team does not have access to LLM '{projectModelUpdate.llm}'"
                )

    if projectModelUpdate.embeddings and not projectModelUpdate.team_id and project.type == "rag":
        current_team = db_wrapper.get_team_by_id(project.team_id)
        if current_team:
            embedding_model = request.app.state.brain.get_embedding(projectModelUpdate.embeddings, db_wrapper)
            if embedding_model and embedding_model.model_name not in [e.name for e in current_team.embeddings]:
                raise HTTPException(
                    status_code=403, detail=f"Team does not have access to embedding model '{projectModelUpdate.embeddings}'"
                )

    if projectModelUpdate.team_id:
        team = db_wrapper.get_team_by_id(projectModelUpdate.team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")

        is_team_member = user.id in [u.id for u in team.users]
        is_team_admin = user.id in [u.id for u in team.admins]
        if not (is_team_member or is_team_admin or user.is_admin):
            raise HTTPException(
                status_code=403, detail="User does not have access to this team"
            )

        llm_name = projectModelUpdate.llm or project.llm
        llm_model = request.app.state.brain.get_llm(llm_name, db_wrapper)
        if llm_model and llm_model.props.name not in [llm.name for llm in team.llms]:
            raise HTTPException(
                status_code=403, detail=f"Team does not have access to LLM '{llm_name}'"
            )

        if project.type == "rag":
            embedding_name = projectModelUpdate.embeddings or project.embeddings
            if embedding_name:
                embedding_model = request.app.state.brain.get_embedding(
                    embedding_name, db_wrapper
                )
                if embedding_model and embedding_model.model_name not in [
                    embedding.name for embedding in team.embeddings
                ]:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Team does not have access to embedding model '{embedding_name}'",
                    )

    if user.is_private and projectModelUpdate.llm:
        llm_model = request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper)
        if llm_model and llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403, detail="User not allowed to use public models"
            )

    # Stdio MCP transport sneaked into options.mcp_servers grants RCE same as /tools/mcp/probe.
    if projectModelUpdate.options and projectModelUpdate.options.mcp_servers:
        for srv in projectModelUpdate.options.mcp_servers:
            check_user_can_use_mcp_host(user, srv.host)

    if projectModelUpdate.options:
        existing_opts = json.loads(project.options) if project.options else {}
        for key in _SENSITIVE_OPTION_KEYS:
            val = getattr(projectModelUpdate.options, key, None)
            if val and val.startswith("****"):
                setattr(projectModelUpdate.options, key, existing_opts.get(key))
        if projectModelUpdate.options.sync_sources and existing_opts.get("sync_sources"):
            existing_sources = {s.get("name"): s for s in existing_opts["sync_sources"] if isinstance(s, dict)}
            for src in projectModelUpdate.options.sync_sources:
                for key in ("s3_access_key", "s3_secret_key", "confluence_api_token", "sharepoint_client_secret", "gdrive_service_account_json"):
                    val = getattr(src, key, None)
                    if val and val.startswith("****"):
                        existing_src = existing_sources.get(src.name, {})
                        setattr(src, key, existing_src.get(key))

    projectModelUpdate._user_id = user.id

    # Drop memory_search collection synchronously on embedding swap so cron rebuilds clean.
    if (
        projectModelUpdate.embeddings is not None
        and projectModelUpdate.embeddings != project.embeddings
    ):
        Project.reset_memory_index(projectID)

    try:
        if db_wrapper.edit_project(projectID, projectModelUpdate):
            return {"project": projectID}
        else:
            raise HTTPException(status_code=404, detail="Project not found")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects", status_code=201, tags=["Projects"])
async def route_create_project(
    request: Request,
    projectModel: ProjectModelCreate,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new AI project."""
    check_not_restricted(user)
    projectModel.name = unidecode(projectModel.name.strip().lower().replace(" ", "_"))
    projectModel.name = re.sub(r"[^\w\-.]+", "", projectModel.name)

    if projectModel.human_name is None:
        projectModel.human_name = projectModel.name

    if projectModel.name.strip() == "":
        raise HTTPException(status_code=400, detail="Invalid project name")

    if not projectModel.team_id:
        raise HTTPException(status_code=400, detail="Team selection is required")

    team = db_wrapper.get_team_by_id(projectModel.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    is_team_member = user.id in [u.id for u in team.users]
    is_team_admin = user.id in [u.id for u in team.admins]
    if not (is_team_member or is_team_admin or user.is_admin):
        raise HTTPException(
            status_code=403, detail="User does not have access to this team"
        )

    # App-builder needs a local Docker socket; bind mounts don't traverse tcp://.
    if projectModel.type == "app":
        docker_url = (getattr(config, "DOCKER_URL", "") or "").strip()
        # Empty docker_url ok (IDE still works, just no preview); reject only tcp://.
        if docker_url.startswith("tcp://"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "App Builder projects require a local Docker socket "
                    "(unix://). Remote tcp:// daemons cannot bind-mount the "
                    "host filesystem and the live preview would not work."
                ),
            )

    if projectModel.type != "block":
        llm_model = request.app.state.brain.get_llm(projectModel.llm, db_wrapper)
        if llm_model is None:
            raise HTTPException(status_code=404, detail="LLM not found")

        if llm_model.props.name not in [llm.name for llm in team.llms]:
            raise HTTPException(
                status_code=403,
                detail=f"Team does not have access to LLM '{projectModel.llm}'",
            )

    if projectModel.type == "rag":
        embedding_model = request.app.state.brain.get_embedding(
            projectModel.embeddings, db_wrapper
        )
        if embedding_model is None:
            raise HTTPException(status_code=404, detail="Embeddings not found")

        if user.is_private and embedding_model.props.privacy != "private":
            raise HTTPException(
                status_code=403, detail="User not allowed to use public models"
            )

        if embedding_model.model_name not in [
            embedding.name for embedding in team.embeddings
        ]:
            raise HTTPException(
                status_code=403,
                detail=f"Team does not have access to embedding model '{projectModel.embeddings}'",
            )

    if (
        db_wrapper.db.query(ProjectDatabase)
        .filter(
            ProjectDatabase.creator == user.id,
            ProjectDatabase.name == projectModel.name,
        )
        .first()
        is not None
    ):
        raise HTTPException(status_code=403, detail="Project already exists")

    if projectModel.type != "block" and user.is_private and llm_model.props.privacy != "private":
        raise HTTPException(
            status_code=403, detail="User not allowed to use public models"
        )

    try:
        project_db = db_wrapper.create_project(
            projectModel.name,
            projectModel.embeddings,
            projectModel.llm,
            projectModel.vectorstore,
            projectModel.human_name,
            projectModel.human_description,
            projectModel.type,
            user.id,
            projectModel.team_id,
        )

        if project_db is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to create project, check team's access to selected LLM and embeddings",
            )

        project = get_project(project_db.id, db_wrapper, request.app.state.brain)

        if project.props.vectorstore:
            project.vector = tools.find_vector_db(project)(
                request.app.state.brain,
                project,
                request.app.state.brain.get_embedding(
                    project.props.embeddings, db_wrapper
                ),
            )

        if projectModel.type == "app":
            from restai.app.storage import seed_hello_world
            try:
                seed_hello_world(project_db.id, projectModel.human_name or projectModel.name)
            except Exception:
                # Don't roll back; user can re-seed by editing any file in the IDE.
                logging.exception("app seed failed for project %s", project_db.id)

        return {"project": project.props.id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/embeddings/reset", tags=["Knowledge"])
async def reset_embeddings(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Reset all embeddings for a RAG project."""
    check_not_restricted(user)
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        project.vector.reset(request.app.state.brain)

        return {"project": project.props.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/embeddings/search", tags=["Knowledge"])
async def find_embedding(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    embedding: FindModel = ...,
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Search embeddings by text similarity or source."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        output = []

        if embedding.text:
            k = embedding.k or project.props.options.k or 2

            if embedding.score is not None:
                threshold = embedding.score
            else:
                threshold = embedding.score or project.props.score or 0.2

            retriever = VectorIndexRetriever(
                index=project.vector.index,
                similarity_top_k=k,
            )

            try:
                nodes = retriever.retrieve(embedding.text)
            except Exception as retrieval_err:
                if "Nothing found on disk" in str(retrieval_err) or "hnsw" in str(retrieval_err).lower():
                    raise HTTPException(status_code=503, detail="Vector index is being rebuilt. Please try again in a moment.")
                raise

            postprocessor = SimilarityPostprocessor(similarity_cutoff=threshold)
            nodes = postprocessor.postprocess_nodes(nodes)

            for node in nodes:
                output.append(
                    {
                        "source": node.metadata.get("source", "unknown"),
                        "score": node.score,
                        "id": node.node_id,
                    }
                )

        elif embedding.source:
            output = project.vector.list_source(embedding.source)

        return {"embeddings": output}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects/{projectID}/embeddings/source/{source}", tags=["Knowledge"])
async def get_embedding(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    source: str = PathParam(description="Base64-encoded source identifier"),
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get embedding chunks for a specific source."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        docs = project.vector.find_source(base64.b64decode(source).decode("utf-8"))

        if len(docs["ids"]) == 0:
            return {"ids": []}
        else:
            return docs
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects/{projectID}/embeddings/id/{embedding_id}", tags=["Knowledge"])
async def get_embedding_by_id(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    embedding_id: str = PathParam(description="Embedding chunk ID"),
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get a specific embedding chunk by ID."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        chunk = project.vector.find_id(embedding_id)
        return chunk
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/clone", status_code=201, tags=["Projects"])
async def clone_project(
    request: Request,
    projectID: int = PathParam(description="Project ID to clone"),
    body: dict = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Clone a project with all its settings, eval datasets, and prompt versions."""
    check_not_restricted(user)
    from restai.models.databasemodels import EvalDatasetDatabase, EvalTestCaseDatabase, PromptVersionDatabase
    from datetime import datetime as dt
    from datetime import timezone as tz

    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name is required")

    source = db_wrapper.get_project_by_id(projectID)
    if source is None:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = db_wrapper.get_project_by_name(new_name)
    if existing:
        raise HTTPException(status_code=409, detail="A project with this name already exists")

    new_project = db_wrapper.create_project(
        name=new_name,
        embeddings=source.embeddings,
        llm=source.llm,
        vectorstore=source.vectorstore,
        human_name=(source.human_name or source.name) + " (copy)",
        human_description=source.human_description,
        project_type=source.type,
        creator=user.id,
        team_id=source.team_id,
    )
    if new_project is None:
        raise HTTPException(status_code=400, detail="Failed to clone project")

    new_project.system = source.system
    new_project.censorship = source.censorship
    new_project.guard = source.guard
    new_project.default_prompt = source.default_prompt
    new_project.public = source.public
    new_project.options = source.options

    db_wrapper.db.commit()

    source_versions = (
        db_wrapper.db.query(PromptVersionDatabase)
        .filter(PromptVersionDatabase.project_id == projectID)
        .order_by(PromptVersionDatabase.version)
        .all()
    )
    for v in source_versions:
        db_wrapper.db.add(PromptVersionDatabase(
            project_id=new_project.id,
            version=v.version,
            system_prompt=v.system_prompt,
            description=v.description,
            created_by=user.id,
            created_at=dt.now(tz.utc),
            is_active=v.is_active,
        ))

    source_datasets = (
        db_wrapper.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.project_id == projectID)
        .all()
    )
    for ds in source_datasets:
        new_ds = EvalDatasetDatabase(
            name=ds.name,
            description=ds.description,
            project_id=new_project.id,
            created_at=dt.now(tz.utc),
            updated_at=dt.now(tz.utc),
        )
        db_wrapper.db.add(new_ds)
        db_wrapper.db.flush()

        source_cases = (
            db_wrapper.db.query(EvalTestCaseDatabase)
            .filter(EvalTestCaseDatabase.dataset_id == ds.id)
            .all()
        )
        for tc in source_cases:
            db_wrapper.db.add(EvalTestCaseDatabase(
                dataset_id=new_ds.id,
                question=tc.question,
                expected_answer=tc.expected_answer,
                context=tc.context,
                created_at=dt.now(tz.utc),
            ))

    db_wrapper.db.commit()

    return {"project": new_project.id}


@router.post(
    "/projects/{projectID}/embeddings/ingest/text", response_model=IngestResponse, tags=["Knowledge"]
)
async def ingest_text(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    ingest: TextIngestModel = ...,
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Ingest raw text into the knowledge base."""
    check_not_restricted(user)
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        metadata = {"source": ingest.source}
        documents = [Document(text=ingest.text, metadata=metadata)]

        if ingest.keywords and len(ingest.keywords) > 0:
            for document in documents:
                document.metadata["keywords"] = ", ".join(ingest.keywords)
        else:
            documents = extract_keywords_for_metadata(documents)

        n_chunks = index_documents_classic(
            project, documents, ingest.splitter, ingest.chunks
        )
        project.vector.save()

        if project.props.options.enable_knowledge_graph:
            full_text = "\n".join(d.text for d in documents)
            background_tasks.add_task(
                extract_and_persist_safe,
                project.props.id, ingest.source, full_text,
                request.app.state.brain, DBWrapper,
            )

        return {
            "source": ingest.source,
            "documents": len(documents),
            "chunks": n_chunks,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/projects/{projectID}/embeddings/ingest/url", response_model=IngestResponse, tags=["Knowledge"]
)
async def ingest_url(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    ingest: URLIngestModel = ...,
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Ingest a web page into the knowledge base."""
    check_not_restricted(user)
    try:
        if ingest.url and not ingest.url.startswith("http"):
            raise HTTPException(
                status_code=400, detail="Specify the protocol http:// or https://"
            )

        # SSRF protection — block requests to private/internal networks
        from restai.helper import _is_private_ip
        from urllib.parse import urlparse as _urlparse
        try:
            hostname = _urlparse(ingest.url).hostname
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid URL")
        if not hostname:
            raise HTTPException(status_code=400, detail="URL has no valid hostname")
        if _is_private_ip(hostname):
            raise HTTPException(
                status_code=400,
                detail="Access to internal/private network addresses is not allowed",
            )

        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        urls = project.vector.list()
        if ingest.url in urls:
            raise HTTPException(status_code=409, detail="URL already ingested. Delete first.")

        loader = SeleniumWebReader()

        documents = loader.load_data(urls=[ingest.url])
        for doc in documents:
            doc.metadata["source"] = ingest.url
        documents = extract_keywords_for_metadata(documents)

        n_chunks = index_documents_classic(
            project, documents, ingest.splitter, ingest.chunks
        )
        project.vector.save()

        if project.props.options.enable_knowledge_graph:
            full_text = "\n".join(d.text for d in documents)
            background_tasks.add_task(
                extract_and_persist_safe,
                project.props.id, ingest.url, full_text,
                request.app.state.brain, DBWrapper,
            )

        return {"source": ingest.url, "documents": len(documents), "chunks": n_chunks}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/projects/{projectID}/embeddings/ingest/upload", response_model=IngestResponse, tags=["Knowledge"]
)
async def ingest_file(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    file: UploadFile = ...,
    options: str = Form("{}"),
    chunks: int = Form(256, ge=32, le=8192),
    splitter: str = Form("sentence"),
    method: str = Form(None),
    classic: bool = Form(None),
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Upload and ingest a file into the knowledge base."""
    check_not_restricted(user)
    if splitter not in ("sentence", "token"):
        raise HTTPException(status_code=422, detail="splitter must be 'sentence' or 'token'")

    contents = await file.read()
    if len(contents) > config.MAX_UPLOAD_SIZE:
        max_mb = config.MAX_UPLOAD_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_mb} MB",
        )
    await file.seek(0)

    project = get_project(projectID, db_wrapper, request.app.state.brain)

    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Only available for RAG projects.")

    opts = json.loads(options)

    resolved_method = method or "auto"
    # Backcompat: `classic` bool overrides when `method` wasn't set.
    if classic is not None and method is None:
        resolved_method = "classic" if classic else "docling"

    from restai.models.models import sanitize_filename
    file.filename = sanitize_filename(file.filename)
    ext = os.path.splitext(file.filename)[1].lower()
    source_name = unidecode(file.filename)

    temp = tempfile.NamedTemporaryFile(delete=False)
    try:
        shutil.copyfileobj(file.file, temp)
    finally:
        temp.close()

    try:
        used_method = resolved_method

        if resolved_method == "auto":
            from restai.loaders.markitdown_loader import auto_ingest
            documents, used_method = auto_ingest(
                temp.name, source_name,
                manager=getattr(request.app.state, "manager", None),
                opts=opts,
            )
            if not documents:
                raise HTTPException(status_code=400, detail="No content could be extracted from the file.")
        elif resolved_method == "markitdown":
            from restai.loaders.markitdown_loader import load_with_markitdown
            documents = load_with_markitdown(temp.name, source=source_name)
            if not documents:
                raise HTTPException(status_code=400, detail="MarkItDown could not extract content from this file.")
        elif resolved_method == "docling":
            from restai.document.runner import load_documents
            documents = load_documents(request.app.state.manager, temp.name)
        else:
            used_method = "classic"
            loader = find_file_loader(ext, opts)
            try:
                documents = loader.load_data(file=Path(temp.name))
            except TypeError:
                documents = loader.load_data(input_file=Path(temp.name))

        documents = extract_keywords_for_metadata(documents)

        for document in documents:
            if "filename" in document.metadata:
                del document.metadata["filename"]
            document.metadata["source"] = source_name

        if used_method in ("markitdown", "docling"):
            n_chunks = index_documents_docling(project, documents)
        else:
            n_chunks = index_documents_classic(project, documents, splitter, chunks)

        project.vector.save()

        if project.props.options.enable_knowledge_graph:
            full_text = "\n".join(d.text for d in documents)
            background_tasks.add_task(
                extract_and_persist_safe,
                project.props.id, source_name, full_text,
                request.app.state.brain, DBWrapper,
            )

        return {
            "source": file.filename,
            "documents": len(documents),
            "chunks": n_chunks,
            "method": used_method,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        try:
            os.unlink(temp.name)
        except OSError:
            pass


@router.get("/projects/{projectID}/embeddings", tags=["Knowledge"])
async def get_embeddings(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all embedding sources for a RAG project."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        if project.vector is not None:
            output = project.vector.list()
        else:
            output = []

        return {"embeddings": output}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/projects/{projectID}/embeddings/{source}", tags=["Knowledge"])
async def delete_embedding(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    source: str = PathParam(description="Base64-encoded source identifier"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete all embeddings for a specific source."""
    check_not_restricted(user)
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        ids = project.vector.delete_source(base64.b64decode(source).decode("utf-8"))

        return {"deleted": len(ids)}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/chat", tags=["Chat"])
async def chat_query(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    q_input: ChatModel = ...,
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Send a chat message to a project with conversation history."""
    try:
        import time as _time
        start_time = _time.perf_counter()

        # Resume the buffered stream ONLY for a genuine reconnect — one that
        # carries the SSE `Last-Event-ID` header (fetchEventSource sets it when
        # it retries a dropped connection). A fresh POST has no `Last-Event-ID`,
        # so it is a NEW user turn even when it reuses the conversation's
        # chat_id, and must NOT replay the previous (already-finished) turn's
        # buffer. That replay is the playground bug where pressing Enter to send
        # a 2nd message re-sent the previous one. Evict any lingering session
        # for this id and fall through to answer the new question.
        if q_input.stream and q_input.id:
            from restai import chat_resume as _resume
            hdr = request.headers.get("last-event-id")
            if hdr:
                existing = await _resume.lookup(q_input.id)
                if existing is not None:
                    try:
                        last_id = int(hdr)
                    except ValueError:
                        last_id = 0
                    from starlette.responses import StreamingResponse as _SR
                    return _SR(
                        existing.subscribe(last_event_id=last_id),
                        media_type="text/event-stream",
                    )
            else:
                await _resume.evict(q_input.id)

        if not q_input.question and not q_input.image:
            raise HTTPException(status_code=400, detail="Missing question")

        project = get_project(projectID, db_wrapper, request.app.state.brain)

        result = await chat_main(
            request,
            request.app.state.brain,
            project,
            q_input,
            user,
            db_wrapper,
            background_tasks,
            start_time=start_time,
        )
        if result is None:
            raise HTTPException(status_code=500, detail="No response generated")
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/chat/stop", tags=["Chat"])
async def chat_stop(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    body: dict = ...,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Cancel an in-flight streaming chat by chat_id.

    Producer-side agent task is detached from the HTTP request so client
    AbortController alone can't stop it (see `restai/chat_resume.py`).
    """
    try:
        chat_id = (body or {}).get("id") if isinstance(body, dict) else None
        if not chat_id:
            raise HTTPException(status_code=400, detail="Missing chat id")
        # Enforce same auth scope as /chat (404s cross-project chat_ids).
        get_project(projectID, db_wrapper, request.app.state.brain)
        from restai import chat_resume as _resume
        sess = await _resume.lookup(chat_id)
        if sess is None:
            # Evict in case of half-state.
            await _resume.evict(chat_id)
            return {"stopped": False, "reason": "no in-flight session"}
        await sess.cancel()
        # Evict NOW so next /chat with same chat_id starts fresh (not resume of dead session).
        await _resume.evict(chat_id)
        return {"stopped": True}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/question", tags=["Chat"], deprecated=True)
async def question_query_endpoint(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    q_input: ChatModel = ...,
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """**Deprecated** — forwards to `/chat` with an ephemeral chat_id.

    Accepts the same body as `/chat` (ChatModel). The response shape is
    preserved (`type: "question"`) for backwards compatibility."""
    try:
        import time as _time
        start_time = _time.perf_counter()

        if not q_input.question and not q_input.image:
            raise HTTPException(status_code=400, detail="Question missing")

        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if user.level == "public":
            q_input = ChatModel(
                question=q_input.question,
                image=q_input.image,
                negative=q_input.negative,
            )

        q_input.id = None

        result = await chat_main(
            request,
            request.app.state.brain,
            project,
            q_input,
            user,
            db_wrapper,
            background_tasks,
            start_time=start_time,
        )
        if result is None:
            raise HTTPException(status_code=500, detail="No response generated")
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/sync/trigger", tags=["Knowledge"])
async def trigger_sync(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Manually trigger a knowledge base sync now."""
    check_not_restricted(user)
    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Sync only available for RAG projects")
    opts = project.props.options
    if not opts or not opts.sync_sources:
        raise HTTPException(status_code=400, detail="No sync sources configured")

    from restai.integrations.sync import run_sync_now
    run_sync_now(projectID, request.app.state.brain)
    return {"message": "Sync triggered"}


@router.get("/projects/{projectID}/sync/status", tags=["Knowledge"])
async def get_sync_status(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get sync status for a project."""
    project = get_project(projectID, db_wrapper, request.app.state.brain)
    opts = project.props.options
    return {
        "enabled": bool(opts.sync_enabled) if opts else False,
        "sources": len(opts.sync_sources) if opts and opts.sync_sources else 0,
    }


@router.get("/projects/{projectID}/tools", tags=["Projects"])
async def get_project_tools(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List available MCP tools for an agent project."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "agent":
            raise HTTPException(
                status_code=400,
                detail="Tools endpoint only available for agent-type projects",
            )

        if not project.props.options or not project.props.options.mcp_servers:
            return {
                "tools": [],
                "message": "No MCP servers configured for this project",
            }

        all_tools = {}

        for mcp_server in project.props.options.mcp_servers:
            server_name = mcp_server.host
            try:
                mcp_client = BasicMCPClient(
                    mcp_server.host,
                    args=mcp_server.args or [],
                    env=mcp_server.env or {},
                    headers=mcp_server.headers or None,
                )

                mcp_tool_spec = McpToolSpec(
                    client=mcp_client,
                )

                tools = await mcp_tool_spec.to_tool_list_async()

                tools_info = []

                for tool in tools:
                    tools_info.append(
                        {
                            "name": tool.metadata.name,
                            "description": tool.metadata.description,
                            "schema": tool.metadata.fn_schema_str,
                        }
                    )

                all_tools[server_name] = {"tools": tools_info}

            except BaseException as e:
                all_tools[server_name] = {
                    "error": str(e),
                    "message": f"Failed to connect to MCP server: {mcp_server.host}",
                }

        return {"mcp_servers": all_tools}

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/invitations", tags=["Projects"])
async def send_project_invitation(
    projectID: int = PathParam(description="Project ID"),
    body: dict = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Invite a user to join a project. Only the project creator or an admin can invite."""
    check_not_restricted(user)

    project_db = db_wrapper.get_project_by_id(projectID)
    if project_db is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not user.is_admin and project_db.creator != user.id:
        raise HTTPException(status_code=403, detail="Only the project creator can invite users")

    response = {"message": "If the user exists and belongs to the team, they will receive the invitation."}

    username = body.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    target = db_wrapper.get_user_by_username(username)
    if target is None:
        return response

    if any(u.id == target.id for u in project_db.users):
        return response

    in_team = target.is_admin
    if not in_team and project_db.team:
        in_team = target in project_db.team.users or target in project_db.team.admins
    if not in_team:
        return response

    existing = (
        db_wrapper.db.query(ProjectInvitationDatabase)
        .filter(
            ProjectInvitationDatabase.project_id == projectID,
            ProjectInvitationDatabase.username == username,
            ProjectInvitationDatabase.status == "pending",
        )
        .first()
    )
    if existing is not None:
        return response

    invite = ProjectInvitationDatabase(
        project_id=projectID,
        username=username,
        invited_by=user.id,
        status="pending",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db_wrapper.db.add(invite)
    db_wrapper.db.commit()

    return response
