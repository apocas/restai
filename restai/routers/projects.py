import base64
import json
import logging
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
)
from restai.database import get_db_wrapper, DBWrapper
from restai.helper import chat_main, question_main
from restai.loaders.url import SeleniumWebReader
from restai.models.models import (
    FindModel,
    IngestResponse,
    ProjectModel,
    ProjectModelCreate,
    ProjectModelUpdate,
    ProjectResponse,
    ProjectsResponse,
    QuestionModel,
    ChatModel,
    TextIngestModel,
    URLIngestModel,
    User,
)
from restai.brain import Brain
from restai.vectordb import tools
from restai.vectordb.tools import (
    find_file_loader,
    extract_keywords_for_metadata,
    index_documents_classic,
    index_documents_docling,
)
from restai.models.databasemodels import OutputDatabase, ProjectDatabase
from restai.settings import mask_key
import datetime
from sqlalchemy import func, Integer, case
import calendar
import tempfile
import shutil

_SENSITIVE_OPTION_KEYS = ("telegram_token", "slack_bot_token", "slack_app_token", "connection")

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


@router.get("/projects", response_model=ProjectsResponse, tags=["Projects"])
async def route_get_projects(
    _: Request,
    v_filter: str = Query("own", alias="filter", description="Filter mode: 'own' for user's projects, 'public' for public projects"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start offset"),
    end: int = Query(50, ge=1, le=100000, description="Pagination end offset"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List projects accessible to the current user."""
    query = db_wrapper.db.query(ProjectDatabase)

    if v_filter == "public":
        query = query.filter(ProjectDatabase.public == True)
    elif not user.is_admin:
        query = query.filter(ProjectDatabase.id.in_(user.get_project_ids()))

    # Filter by API key scope if set
    if user.api_key_allowed_projects is not None:
        query = query.filter(ProjectDatabase.id.in_(user.api_key_allowed_projects))

    projects = query.offset(start).limit(end - start).all()

    # Process the projects to simplify team objects
    serialized_projects = []
    for project in projects:
        # Create a Pydantic model from the SQLAlchemy object (handles all properties dynamically)
        project_model = ProjectModel.model_validate(project)

        # Convert to dict and modify just the team property
        project_dict = project_model.model_dump()

        # Simplify the team object if it exists
        if project_dict.get("team"):
            project_dict["team"] = {
                "id": project_dict["team"]["id"],
                "name": project_dict["team"]["name"],
            }

        # Mask sensitive tokens in list
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

    # Get accessible project IDs
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

    # Bulk query 1: activity + latency (last 7 days)
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

    # Bulk query 2: guard block rate (last 30 days)
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

    # Bulk query 3: latest eval scores
    # Get the most recent completed run per project
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

    # Compute health scores
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

        # Latency score (30%)
        if avg_latency is not None:
            if avg_latency < 500:
                latency_score = 1.0
            elif avg_latency < 2000:
                latency_score = 0.5
            else:
                latency_score = 0.0
        else:
            latency_score = 0.5

        # Activity score (30%)
        if requests_7d > 10:
            activity_score = 1.0
        elif requests_7d > 0:
            activity_score = 0.5
        else:
            activity_score = 0.0

        # Guard score (20%)
        if block_rate is not None:
            if block_rate < 0.05:
                guard_score = 1.0
            elif block_rate < 0.15:
                guard_score = 0.5
            else:
                guard_score = 0.0
        else:
            guard_score = 0.5

        # Eval score (20%)
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
            case "inference":
                final_output["system"] = output["system"] or ""
            case "agent":
                final_output["system"] = output["system"] or ""
        if llm_model:
            final_output["llm_type"] = llm_model.props.type
            final_output["llm_privacy"] = llm_model.props.privacy

        # Mask sensitive tokens
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
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a project and all associated data."""
    try:
        proj = get_project(projectID, db_wrapper, request.app.state.brain)

        # Stop Telegram poller if running
        if proj.props.options and proj.props.options.telegram_token:
            from restai.telegram import stop_poller
            stop_poller(projectID)

        # Stop Slack bot if running
        if proj.props.options and proj.props.options.slack_bot_token:
            from restai.slack_bot import stop_slack_bot
            stop_slack_bot(projectID)

        proj.delete()

        db_wrapper.db.query(OutputDatabase).filter(
            OutputDatabase.project_id == proj.props.id
        ).delete()

        db_wrapper.delete_project(db_wrapper.get_project_by_id(projectID))

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
    # Check if the project exists
    project = db_wrapper.get_project_by_id(projectID)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate LLM if being updated
    if (
        projectModelUpdate.llm
        and request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper) is None
    ):
        raise HTTPException(status_code=404, detail="LLM not found")

    # Validate team LLM/embedding access even when team_id is not changing
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

    # Validate team if being updated
    if projectModelUpdate.team_id:
        # Check if the new team exists
        team = db_wrapper.get_team_by_id(projectModelUpdate.team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")

        # Verify user belongs to the new team or is an admin
        is_team_member = user.id in [u.id for u in team.users]
        is_team_admin = user.id in [u.id for u in team.admins]
        if not (is_team_member or is_team_admin or user.is_admin):
            raise HTTPException(
                status_code=403, detail="User does not have access to this team"
            )

        # Validate team has access to the LLM
        llm_name = projectModelUpdate.llm or project.llm
        llm_model = request.app.state.brain.get_llm(llm_name, db_wrapper)
        if llm_model and llm_model.props.name not in [llm.name for llm in team.llms]:
            raise HTTPException(
                status_code=403, detail=f"Team does not have access to LLM '{llm_name}'"
            )

        # Validate team has access to embeddings for RAG projects
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

    # Validate private user restrictions
    if user.is_private:
        llm_model = request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper)
        if llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403, detail="User not allowed to use public models"
            )

    # Handle masked tokens — preserve existing values
    if projectModelUpdate.options:
        existing_opts = json.loads(project.options) if project.options else {}
        for key in _SENSITIVE_OPTION_KEYS:
            val = getattr(projectModelUpdate.options, key, None)
            if val and val.startswith("****"):
                setattr(projectModelUpdate.options, key, existing_opts.get(key))
        # Restore masked credentials in sync sources
        if projectModelUpdate.options.sync_sources and existing_opts.get("sync_sources"):
            existing_sources = {s.get("name"): s for s in existing_opts["sync_sources"] if isinstance(s, dict)}
            for src in projectModelUpdate.options.sync_sources:
                for key in ("s3_access_key", "s3_secret_key", "confluence_api_token", "sharepoint_client_secret", "gdrive_service_account_json"):
                    val = getattr(src, key, None)
                    if val and val.startswith("****"):
                        existing_src = existing_sources.get(src.name, {})
                        setattr(src, key, existing_src.get(key))

    # Attach user ID for prompt version tracking
    projectModelUpdate._user_id = user.id

    try:
        if db_wrapper.edit_project(projectID, projectModelUpdate):
            # Start/stop Telegram poller based on token changes
            if projectModelUpdate.options:
                from restai.telegram import start_poller, stop_poller, validate_token

                saved_opts = json.loads(
                    db_wrapper.get_project_by_id(projectID).options or "{}"
                )
                saved_token = saved_opts.get("telegram_token")

                if saved_token:
                    try:
                        validate_token(saved_token)
                        start_poller(projectID, saved_token, request.app)
                    except Exception as e:
                        logging.warning(
                            f"Failed to start Telegram poller for project {projectID}: {e}"
                        )
                else:
                    stop_poller(projectID)

                # Start/stop Slack bot based on token changes
                from restai.slack_bot import start_slack_bot, stop_slack_bot
                slack_bot_token = saved_opts.get("slack_bot_token")
                slack_app_token = saved_opts.get("slack_app_token")
                if slack_bot_token and slack_app_token:
                    try:
                        start_slack_bot(projectID, slack_bot_token, slack_app_token, request.app)
                    except Exception as e:
                        logging.warning(f"Failed to start Slack bot for project {projectID}: {e}")
                else:
                    stop_slack_bot(projectID)

                # Start/stop sync worker based on sync config changes
                from restai.sync import start_sync, stop_sync
                sync_enabled = saved_opts.get("sync_enabled")
                sync_sources = saved_opts.get("sync_sources")
                if sync_enabled and sync_sources:
                    start_sync(projectID, request.app)
                else:
                    stop_sync(projectID)

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
    projectModel.name = unidecode(projectModel.name.strip().lower().replace(" ", "_"))
    projectModel.name = re.sub(r"[^\w\-.]+", "", projectModel.name)

    if projectModel.human_name is None:
        projectModel.human_name = projectModel.name

    if projectModel.name.strip() == "":
        raise HTTPException(status_code=400, detail="Invalid project name")

    # Validate that a team ID is provided
    if not projectModel.team_id:
        raise HTTPException(status_code=400, detail="Team selection is required")

    # Check if the team exists
    team = db_wrapper.get_team_by_id(projectModel.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    # Verify user belongs to the team or is an admin
    is_team_member = user.id in [u.id for u in team.users]
    is_team_admin = user.id in [u.id for u in team.admins]
    if not (is_team_member or is_team_admin or user.is_admin):
        raise HTTPException(
            status_code=403, detail="User does not have access to this team"
        )

    if config.RESTAI_DEMO == True and not user.is_admin:
        if projectModel.type == "agent":
            raise HTTPException(
                status_code=403,
                detail="Demo mode, not allowed to create this type of projects.",
            )

    # Block projects don't require an LLM
    if projectModel.type != "block":
        # Validate LLM exists
        llm_model = request.app.state.brain.get_llm(projectModel.llm, db_wrapper)
        if llm_model is None:
            raise HTTPException(status_code=404, detail="LLM not found")

        # Validate team has access to the LLM
        if llm_model.props.name not in [llm.name for llm in team.llms]:
            raise HTTPException(
                status_code=403,
                detail=f"Team does not have access to LLM '{projectModel.llm}'",
            )

    # Validate embeddings for RAG projects
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

        # Validate team has access to the embeddings
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

        user_db = db_wrapper.get_user_by_id(user.id)
        user_db.projects.append(project_db)
        db_wrapper.db.commit()
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
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Reset all embeddings for a RAG project."""
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

            nodes = retriever.retrieve(embedding.text)

            postprocessor = SimilarityPostprocessor(similarity_cutoff=threshold)
            nodes = postprocessor.postprocess_nodes(nodes)

            for node in nodes:
                output.append(
                    {
                        "source": node.metadata["source"],
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
    from restai.models.databasemodels import EvalDatasetDatabase, EvalTestCaseDatabase, PromptVersionDatabase
    from datetime import datetime as dt
    from datetime import timezone as tz

    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name is required")

    # Load source project
    source = db_wrapper.get_project_by_id(projectID)
    if source is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check name uniqueness
    existing = db_wrapper.get_project_by_name(new_name)
    if existing:
        raise HTTPException(status_code=409, detail="A project with this name already exists")

    # Create the new project
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

    # Copy settings that create_project doesn't handle
    new_project.system = source.system
    new_project.censorship = source.censorship
    new_project.guard = source.guard
    new_project.default_prompt = source.default_prompt
    new_project.public = source.public
    new_project.options = source.options

    # Assign to current user
    user_db = db_wrapper.get_user_by_id(user.id)
    if user_db and new_project not in user_db.projects:
        user_db.projects.append(new_project)

    db_wrapper.db.commit()

    # Clone prompt versions
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

    # Clone eval datasets with test cases
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
        db_wrapper.db.flush()  # Get new_ds.id

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


@router.delete("/projects/{projectID}/cache", tags=["Projects"])
async def clear_project_cache(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Clear the project's response cache."""
    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.cache:
        project.cache.clear()
        return {"cleared": True, "project": projectID}
    return {"cleared": False, "detail": "Cache not enabled for this project"}


@router.post(
    "/projects/{projectID}/embeddings/ingest/text", response_model=IngestResponse, tags=["Knowledge"]
)
async def ingest_text(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    ingest: TextIngestModel = ...,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Ingest raw text into the knowledge base."""
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

        # for document in documents:
        #    document.text = document.text.decode('utf-8')

        n_chunks = index_documents_classic(
            project, documents, ingest.splitter, ingest.chunks
        )
        project.vector.save()

        # Invalidate cache when knowledge base changes
        if project.cache:
            project.cache.clear()

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
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Ingest a web page into the knowledge base."""
    if config.RESTAI_DEMO == True and not user.is_admin:
        raise HTTPException(
            status_code=403, detail="Demo mode, not allowed to ingest from an URL."
        )

    try:
        if ingest.url and not ingest.url.startswith("http"):
            raise HTTPException(
                status_code=400, detail="Specify the protocol http:// or https://"
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
        documents = extract_keywords_for_metadata(documents)

        n_chunks = index_documents_classic(
            project, documents, ingest.splitter, ingest.chunks
        )
        project.vector.save()

        # Invalidate cache when knowledge base changes
        if project.cache:
            project.cache.clear()

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
    classic: bool = Form(False),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Upload and ingest a file into the knowledge base."""
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

    from restai.models.models import sanitize_filename
    file.filename = sanitize_filename(file.filename)
    ext = os.path.splitext(file.filename)[1].lower()

    temp = tempfile.NamedTemporaryFile(delete=False)
    try:
        shutil.copyfileobj(file.file, temp)
    finally:
        temp.close()

    if classic == True:
        loader = find_file_loader(ext, opts)

        try:
            documents = loader.load_data(file=Path(temp.name))
        except TypeError as e:
            documents = loader.load_data(input_file=Path(temp.name))
        except Exception as e:
            logging.error(e)
            traceback.print_tb(e.__traceback__)
            raise HTTPException(status_code=500, detail="Error while loading file.")
    else:
        try:
            from restai.document.runner import load_documents

            documents = load_documents(request.app.state.manager, temp.name)
        except Exception as e:
            if "File format not allowed" in str(e):
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file format. Retry in classic mode.",
                )
            else:
                raise e

    try:
        documents = extract_keywords_for_metadata(documents)

        for document in documents:
            if "filename" in document.metadata:
                del document.metadata["filename"]
            document.metadata["source"] = unidecode(file.filename)

        if classic == True:
            n_chunks = index_documents_classic(project, documents, splitter, chunks)
        else:
            n_chunks = index_documents_docling(project, documents)

        project.vector.save()

        # Invalidate cache when knowledge base changes
        if project.cache:
            project.cache.clear()

        return {
            "source": file.filename,
            "documents": len(documents),
            "chunks": n_chunks,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


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
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete all embeddings for a specific source."""
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        ids = project.vector.delete_source(base64.b64decode(source).decode("utf-8"))

        # Invalidate cache when knowledge base changes
        if project.cache:
            project.cache.clear()

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

        if not q_input.question and not q_input.image:
            raise HTTPException(status_code=400, detail="Missing question")

        project = get_project(projectID, db_wrapper, request.app.state.brain)

        return await chat_main(
            request,
            request.app.state.brain,
            project,
            q_input,
            user,
            db_wrapper,
            background_tasks,
            start_time=start_time,
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/question", tags=["Chat"])
async def question_query_endpoint(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    q_input: QuestionModel = ...,
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Send a one-shot question to a project."""
    try:
        import time as _time
        start_time = _time.perf_counter()

        if not q_input.question and not q_input.image:
            raise HTTPException(status_code=400, detail="Question missing")

        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if user.level == "public":
            q_input = QuestionModel(
                question=q_input.question,
                image=q_input.image,
                negative=q_input.negative,
            )

        return await question_main(
            request,
            request.app.state.brain,
            project,
            q_input,
            user,
            db_wrapper,
            background_tasks,
            start_time=start_time,
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


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


@router.get("/projects/{projectID}/guards/summary", tags=["Guards"])
async def get_guard_summary(
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get guard event summary statistics for a project."""
    from restai.models.databasemodels import GuardEventDatabase

    total = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID
    ).scalar() or 0

    blocks = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action == "block",
    ).scalar() or 0

    warns = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action == "warn",
    ).scalar() or 0

    input_blocks = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action.in_(["block", "warn"]),
        GuardEventDatabase.phase == "input",
    ).scalar() or 0

    output_blocks = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action.in_(["block", "warn"]),
        GuardEventDatabase.phase == "output",
    ).scalar() or 0

    return {
        "total_checks": total,
        "total_blocks": blocks,
        "block_rate": round(blocks / total, 4) if total > 0 else 0,
        "input_blocks": input_blocks,
        "output_blocks": output_blocks,
        "warn_count": warns,
    }


@router.get("/projects/{projectID}/guards/daily", tags=["Guards"])
async def get_guard_daily(
    projectID: int = PathParam(description="Project ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year"),
    month: int = Query(None, ge=1, le=12, description="Month"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get daily guard event counts for charting."""
    import datetime as dt
    import calendar
    from restai.models.databasemodels import GuardEventDatabase

    now = dt.datetime.now(dt.timezone.utc)
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    start_date = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    end_date = dt.datetime(year, month, last_day, 23, 59, 59, tzinfo=dt.timezone.utc)

    rows = (
        db_wrapper.db.query(
            func.date(GuardEventDatabase.date).label("date"),
            func.count(GuardEventDatabase.id).label("checks"),
            func.sum(case((GuardEventDatabase.action == "block", 1), else_=0)).label("blocks"),
            func.sum(case((GuardEventDatabase.action == "warn", 1), else_=0)).label("warns"),
        )
        .filter(
            GuardEventDatabase.project_id == projectID,
            GuardEventDatabase.date >= start_date,
            GuardEventDatabase.date <= end_date,
        )
        .group_by(func.date(GuardEventDatabase.date))
        .all()
    )

    return {
        "events": [
            {
                "date": r.date,
                "checks": r.checks,
                "blocks": r.blocks or 0,
                "warns": r.warns or 0,
            }
            for r in rows
        ]
    }


@router.get("/projects/{projectID}/guards/events", tags=["Guards"])
async def get_guard_events(
    projectID: int = PathParam(description="Project ID"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start"),
    end: int = Query(20, ge=1, le=100000, description="Pagination end"),
    phase: str = Query(None, description="Filter by phase: input/output"),
    action: str = Query(None, description="Filter by action: block/pass/warn"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get paginated guard events for a project."""
    from restai.models.databasemodels import GuardEventDatabase
    from restai.models.models import GuardEventResponse

    query = db_wrapper.db.query(GuardEventDatabase).filter(
        GuardEventDatabase.project_id == projectID
    )
    if phase:
        query = query.filter(GuardEventDatabase.phase == phase)
    if action:
        query = query.filter(GuardEventDatabase.action == action)

    total = query.count()
    events = query.order_by(GuardEventDatabase.date.desc()).offset(start).limit(end - start).all()

    return {
        "events": [GuardEventResponse.model_validate(e) for e in events],
        "total": total,
    }


@router.get("/projects/{projectID}/analytics/sources", tags=["Statistics"])
async def get_source_analytics(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get per-source retrieval analytics for a RAG project."""
    import datetime as dt
    from restai.models.databasemodels import RetrievalEventDatabase

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Source analytics only available for RAG projects")

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    # Per-source stats
    rows = (
        db_wrapper.db.query(
            RetrievalEventDatabase.source,
            func.count(RetrievalEventDatabase.id).label("retrievals"),
            func.avg(RetrievalEventDatabase.score).label("avg_score"),
        )
        .filter(
            RetrievalEventDatabase.project_id == projectID,
            RetrievalEventDatabase.date >= since,
        )
        .group_by(RetrievalEventDatabase.source)
        .order_by(func.count(RetrievalEventDatabase.id).desc())
        .all()
    )

    sources = [
        {
            "source": r.source,
            "retrievals": r.retrievals,
            "avg_score": round(r.avg_score, 3) if r.avg_score else 0,
        }
        for r in rows
    ]

    # Find never-retrieved documents
    retrieved_sources = {r.source for r in rows}
    all_sources = set()
    if project.vector:
        try:
            all_sources = set(project.vector.list())
        except Exception:
            pass

    never_retrieved = sorted(all_sources - retrieved_sources)

    return {
        "sources": sources,
        "never_retrieved": never_retrieved,
    }


def _nearest_chunk_size(token_count: int) -> int:
    """Snap a token count to the nearest standard chunk size."""
    standard_sizes = [64, 128, 256, 512, 1024, 2048]
    return min(standard_sizes, key=lambda s: abs(s - token_count))


@router.get("/projects/{projectID}/analytics/chunking", tags=["Statistics"])
async def get_chunking_analytics(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Analyze chunk size distributions and retrieval patterns to recommend optimal chunk sizes."""
    import datetime as dt
    from restai.models.databasemodels import RetrievalEventDatabase
    from restai.tools import tokens_from_string

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Chunking analytics only available for RAG projects")

    MAX_CHUNKS = 50000
    truncated = False

    # Part A: Vectorstore chunk size distribution
    all_chunks = []
    if project.vector:
        try:
            all_chunks = project.vector.list_all_chunks(limit=MAX_CHUNKS)
            if len(all_chunks) >= MAX_CHUNKS:
                truncated = True
        except Exception:
            pass

    chunk_token_lengths = []
    for chunk in all_chunks:
        text = chunk.get("text", "")
        if text:
            try:
                tl = tokens_from_string(text)
            except Exception:
                tl = len(text) // 4
            chunk_token_lengths.append(tl)

    buckets = [0, 64, 128, 256, 512, 1024, 2048]
    bucket_labels = []
    bucket_counts = []
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        label = f"{low}-{high}"
        count = sum(1 for tl in chunk_token_lengths if low <= tl < high)
        bucket_labels.append(label)
        bucket_counts.append(count)
    overflow = sum(1 for tl in chunk_token_lengths if tl >= buckets[-1])
    if overflow or not bucket_labels:
        bucket_labels.append(f"{buckets[-1]}+")
        bucket_counts.append(overflow)

    total_chunks_count = len(chunk_token_lengths)
    avg_chunk_tokens = round(sum(chunk_token_lengths) / max(total_chunks_count, 1))
    sorted_lengths = sorted(chunk_token_lengths)
    median_chunk_tokens = sorted_lengths[total_chunks_count // 2] if sorted_lengths else 0

    # Part B: Retrieval event analysis
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    retrieval_rows = (
        db_wrapper.db.query(
            RetrievalEventDatabase.chunk_id,
            RetrievalEventDatabase.chunk_token_length,
            RetrievalEventDatabase.score,
        )
        .filter(
            RetrievalEventDatabase.project_id == projectID,
            RetrievalEventDatabase.date >= since,
        )
        .all()
    )

    retrieved_chunk_ids = set()
    retrieved_token_lengths = []
    retrieved_scores = []
    for row in retrieval_rows:
        if row.chunk_id:
            retrieved_chunk_ids.add(row.chunk_id)
        if row.chunk_token_length:
            retrieved_token_lengths.append(row.chunk_token_length)
        if row.score is not None:
            retrieved_scores.append(row.score)

    ret_bucket_counts = []
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        count = sum(1 for tl in retrieved_token_lengths if low <= tl < high)
        ret_bucket_counts.append(count)
    ret_bucket_counts.append(sum(1 for tl in retrieved_token_lengths if tl >= buckets[-1]))

    avg_retrieved_tokens = round(sum(retrieved_token_lengths) / max(len(retrieved_token_lengths), 1)) if retrieved_token_lengths else None
    avg_score = round(sum(retrieved_scores) / max(len(retrieved_scores), 1), 3) if retrieved_scores else None

    score_by_bucket = []
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        scores_in_bucket = [
            row.score for row in retrieval_rows
            if row.chunk_token_length and low <= row.chunk_token_length < high and row.score is not None
        ]
        score_by_bucket.append({
            "bucket": f"{low}-{high}",
            "avg_score": round(sum(scores_in_bucket) / len(scores_in_bucket), 3) if scores_in_bucket else None,
            "count": len(scores_in_bucket),
        })

    all_chunk_ids = {c["id"] for c in all_chunks}
    never_retrieved_chunks = len(all_chunk_ids - retrieved_chunk_ids) if all_chunk_ids else 0
    retrieval_rate = round(len(retrieved_chunk_ids) / max(len(all_chunk_ids), 1), 3) if all_chunk_ids else 0

    # Part C: Recommendations
    recommendations = []

    if avg_retrieved_tokens and avg_chunk_tokens:
        ratio = avg_retrieved_tokens / avg_chunk_tokens
        if ratio < 0.7:
            suggested = _nearest_chunk_size(avg_retrieved_tokens)
            recommendations.append({
                "type": "reduce_chunk_size",
                "severity": "high" if ratio < 0.5 else "medium",
                "message": (
                    f"Your average chunk is {avg_chunk_tokens} tokens, but retrieved chunks "
                    f"average {avg_retrieved_tokens} tokens. Consider using {suggested}-token chunks "
                    f"for better precision."
                ),
                "suggested_chunk_size": suggested,
            })
        elif ratio > 1.3:
            suggested = _nearest_chunk_size(avg_retrieved_tokens)
            recommendations.append({
                "type": "increase_chunk_size",
                "severity": "medium",
                "message": (
                    f"Retrieved chunks average {avg_retrieved_tokens} tokens, larger than your "
                    f"typical chunk of {avg_chunk_tokens} tokens. Consider increasing to "
                    f"{suggested} tokens for more context per retrieval."
                ),
                "suggested_chunk_size": suggested,
            })

    if retrieval_rate < 0.3 and total_chunks_count > 10:
        recommendations.append({
            "type": "low_retrieval_rate",
            "severity": "medium",
            "message": (
                f"Only {round(retrieval_rate * 100)}% of chunks have been retrieved in the last "
                f"{days} days. Many chunks may be redundant or poorly sized."
            ),
        })

    best_bucket = max(
        (b for b in score_by_bucket if b["avg_score"] is not None and b["count"] >= 3),
        key=lambda b: b["avg_score"],
        default=None,
    )
    if best_bucket:
        recommendations.append({
            "type": "best_scoring_range",
            "severity": "info",
            "message": (
                f"Chunks in the {best_bucket['bucket']} token range have the highest average "
                f"retrieval score ({best_bucket['avg_score']}). Consider targeting this range."
            ),
        })

    return {
        "total_chunks": total_chunks_count,
        "truncated": truncated,
        "avg_chunk_tokens": avg_chunk_tokens,
        "median_chunk_tokens": median_chunk_tokens,
        "size_distribution": {
            "buckets": bucket_labels,
            "counts": bucket_counts,
        },
        "retrieval_analysis": {
            "total_retrievals": len(retrieval_rows),
            "unique_chunks_retrieved": len(retrieved_chunk_ids),
            "retrieval_rate": retrieval_rate,
            "never_retrieved_chunks": never_retrieved_chunks,
            "avg_retrieved_tokens": avg_retrieved_tokens,
            "avg_score": avg_score,
            "size_distribution": {
                "buckets": bucket_labels,
                "counts": ret_bucket_counts,
            },
            "score_by_size": score_by_bucket,
        },
        "recommendations": recommendations,
        "days": days,
    }


@router.post("/projects/{projectID}/sync/trigger", tags=["Knowledge"])
async def trigger_sync(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Manually trigger a knowledge base sync now."""
    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Sync only available for RAG projects")
    opts = project.props.options
    if not opts or not opts.sync_sources:
        raise HTTPException(status_code=400, detail="No sync sources configured")

    from restai.sync import run_sync_now
    run_sync_now(projectID, request.app)
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
    from restai.sync import is_sync_running
    return {
        "enabled": bool(opts.sync_enabled) if opts else False,
        "running": is_sync_running(projectID),
        "last_sync": opts.last_sync if opts else None,
        "sources": len(opts.sync_sources) if opts and opts.sync_sources else 0,
    }


@router.get("/projects/{projectID}/analytics/conversations", tags=["Statistics"])
async def get_conversation_analytics(
    projectID: int = PathParam(description="Project ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year"),
    month: int = Query(None, ge=1, le=12, description="Month"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get conversation analytics for a project."""
    import datetime as dt
    import calendar
    from restai.models.databasemodels import UserDatabase

    now = dt.datetime.now(dt.timezone.utc)
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    start_date = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    end_date = dt.datetime(year, month, last_day, 23, 59, 59, tzinfo=dt.timezone.utc)

    base_filter = [
        OutputDatabase.project_id == projectID,
        OutputDatabase.date >= start_date,
        OutputDatabase.date <= end_date,
    ]

    # Summary
    total_messages = db_wrapper.db.query(func.count(OutputDatabase.id)).filter(*base_filter).scalar() or 0
    total_conversations = db_wrapper.db.query(func.count(func.distinct(OutputDatabase.chat_id))).filter(
        *base_filter, OutputDatabase.chat_id.isnot(None)
    ).scalar() or 0
    avg_latency = db_wrapper.db.query(func.avg(OutputDatabase.latency_ms)).filter(*base_filter).scalar()
    total_tokens = db_wrapper.db.query(
        func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens)
    ).filter(*base_filter).scalar() or 0
    total_cost = db_wrapper.db.query(
        func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost)
    ).filter(*base_filter).scalar() or 0

    summary = {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "avg_messages_per_conversation": round(total_messages / total_conversations, 1) if total_conversations > 0 else 0,
        "avg_latency_ms": round(avg_latency) if avg_latency else 0,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
    }

    # Daily
    daily_rows = (
        db_wrapper.db.query(
            func.date(OutputDatabase.date).label("date"),
            func.count(func.distinct(OutputDatabase.chat_id)).label("conversations"),
            func.count(OutputDatabase.id).label("messages"),
        )
        .filter(*base_filter)
        .group_by(func.date(OutputDatabase.date))
        .order_by(func.date(OutputDatabase.date))
        .all()
    )
    daily = [{"date": r.date, "conversations": r.conversations, "messages": r.messages} for r in daily_rows]

    # Hourly distribution
    hourly_rows = (
        db_wrapper.db.query(
            func.extract("hour", OutputDatabase.date).label("hour"),
            func.count(OutputDatabase.id).label("messages"),
        )
        .filter(*base_filter)
        .group_by(func.extract("hour", OutputDatabase.date))
        .order_by(func.extract("hour", OutputDatabase.date))
        .all()
    )
    hourly_map = {int(r.hour): r.messages for r in hourly_rows}
    hourly = [{"hour": h, "messages": hourly_map.get(h, 0)} for h in range(24)]

    # Top users
    top_user_rows = (
        db_wrapper.db.query(
            OutputDatabase.user_id,
            UserDatabase.username,
            func.count(OutputDatabase.id).label("messages"),
        )
        .join(UserDatabase, OutputDatabase.user_id == UserDatabase.id)
        .filter(*base_filter)
        .group_by(OutputDatabase.user_id, UserDatabase.username)
        .order_by(func.count(OutputDatabase.id).desc())
        .limit(10)
        .all()
    )
    top_users = [{"user_id": r.user_id, "username": r.username, "messages": r.messages} for r in top_user_rows]

    return {
        "summary": summary,
        "daily": daily,
        "hourly": hourly,
        "top_users": top_users,
    }


@router.get("/projects/{projectID}/logs", tags=["Statistics"])
async def get_token_consumption(
    projectID: int = PathParam(description="Project ID"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start offset"),
    end: int = Query(10, ge=1, le=100000, description="Pagination end offset"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get inference logs for a project."""
    try:
        project = db_wrapper.get_project_by_id(projectID)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        logs = (
            db_wrapper.db.query(OutputDatabase)
            .filter_by(project_id=project.id)
            .order_by(OutputDatabase.date.desc())
            .offset(start)
            .limit(end - start)
            .all()
        )
        return {"logs": logs}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects/{projectID}/tokens/daily", tags=["Statistics"])
async def get_monthly_token_consumption(
    projectID: int = PathParam(description="Project ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year for the report (defaults to current year)"),
    month: int = Query(None, ge=1, le=12, description="Month for the report (defaults to current month)"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get daily token consumption for a project."""
    try:
        project = db_wrapper.get_project_by_id(projectID)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        now = datetime.datetime.now(datetime.timezone.utc)
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        start_date = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime.datetime(
            year, month, last_day, 23, 59, 59, tzinfo=datetime.timezone.utc
        )

        token_consumptions = (
            db_wrapper.db.query(
                func.date(OutputDatabase.date).label("date"),
                func.sum(OutputDatabase.input_tokens).label("input_tokens"),
                func.sum(OutputDatabase.output_tokens).label("output_tokens"),
                func.sum(OutputDatabase.input_cost).label("input_cost"),
                func.sum(OutputDatabase.output_cost).label("output_cost"),
                func.avg(OutputDatabase.latency_ms).label("avg_latency_ms"),
            )
            .filter(
                OutputDatabase.project_id == project.id,
                OutputDatabase.date >= start_date,
                OutputDatabase.date <= end_date,
            )
            .group_by(func.date(OutputDatabase.date))
            .all()
        )

        return {
            "tokens": [
                {
                    "date": tc.date,
                    "input_tokens": tc.input_tokens,
                    "output_tokens": tc.output_tokens,
                    "input_cost": tc.input_cost,
                    "output_cost": tc.output_cost,
                    "avg_latency_ms": round(tc.avg_latency_ms) if tc.avg_latency_ms else 0,
                }
                for tc in token_consumptions
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects/{projectID}/tools", tags=["Projects"])
async def get_project_tools(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List available MCP tools for an agent project."""
    try:
        # Get the project by ID
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        # Check if the project is of type agent
        if project.props.type != "agent":
            raise HTTPException(
                status_code=400,
                detail="Tools endpoint only available for agent-type projects",
            )

        # Check if the project has MCP servers configured
        if not project.props.options or not project.props.options.mcp_servers:
            return {
                "tools": [],
                "message": "No MCP servers configured for this project",
            }

        # Dictionary to store tools per MCP server
        all_tools = {}

        # Connect to each MCP server and retrieve tools
        for mcp_server in project.props.options.mcp_servers:
            server_name = mcp_server.host
            try:
                # Create MCP client
                mcp_client = BasicMCPClient(
                    mcp_server.host,
                    args=mcp_server.args or [],
                    env=mcp_server.env or {},
                )

                mcp_tool_spec = McpToolSpec(
                    client=mcp_client,
                )

                # Use the asynchronous version instead of the synchronous one
                tools = await mcp_tool_spec.to_tool_list_async()

                # Get available tools
                tools_info = []

                for tool in tools:
                    tools_info.append(
                        {
                            "name": tool.metadata.name,
                            "description": tool.metadata.description,
                            "schema": tool.metadata.fn_schema_str,
                        }
                    )

                # Add tools to the result
                all_tools[server_name] = {"tools": tools_info}

            except Exception as e:
                # Handle connection errors
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
