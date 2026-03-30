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

        # Mask telegram token in list
        if isinstance(project_dict.get("options"), dict):
            token = project_dict["options"].get("telegram_token")
            if token:
                project_dict["options"]["telegram_token"] = mask_key(token)

        serialized_projects.append(project_dict)

    return {
        "projects": serialized_projects,
        "total": query.count(),
        "start": start,
        "end": end,
    }


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

        # Mask telegram token
        if isinstance(final_output.get("options"), dict):
            token = final_output["options"].get("telegram_token")
            if token:
                final_output["options"]["telegram_token"] = mask_key(token)

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

    # Handle masked Telegram token — preserve existing value
    if projectModelUpdate.options:
        existing_opts = json.loads(project.options) if project.options else {}
        new_telegram_token = projectModelUpdate.options.telegram_token
        if new_telegram_token and new_telegram_token.startswith("****"):
            projectModelUpdate.options.telegram_token = existing_opts.get("telegram_token")

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
