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
    Request,
    UploadFile,
    BackgroundTasks,
    Query,
)
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document
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
    ProjectModelCreate,
    ProjectModelUpdate,
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
from modules.embeddings import EMBEDDINGS
from restai.models.databasemodels import OutputDatabase, ProjectDatabase
import datetime
from sqlalchemy import func
import calendar
import tempfile
import shutil


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()


def get_project(projectID: int, db_wrapper: DBWrapper, brain: Brain):
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects", response_model=ProjectsResponse)
async def route_get_projects(
    _: Request,
    v_filter: str = Query("own", alias="filter"),
    start: int = Query(0),
    end: int = Query(50),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    query = db_wrapper.db.query(ProjectDatabase)
    
    if v_filter == "public":
        query = query.filter(ProjectDatabase.public == True)
    elif not user.is_admin:
        query = query.filter(
            (ProjectDatabase.creator == user.id) | 
            (ProjectDatabase.id.in_([p.id for p in user.projects]))
        )

    projects = query.offset(start).limit(end - start).all()
    return {"projects": projects, "total": query.count(), "start": start, "end": end}


@router.get("/projects/{projectID}")
async def route_get_project(
    request: Request,
    projectID: int,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        output = project.model.model_dump()
        final_output = {}

        try:
            llm_model = request.app.state.brain.get_llm(project.model.llm, db_wrapper)
        except Exception:
            llm_model = None

        final_output["id"] = output["id"]
        final_output["name"] = output["name"]
        final_output["type"] = output["type"]
        final_output["llm"] = output["llm"]
        final_output["human_name"] = output["human_name"]
        final_output["human_description"] = output["human_description"] or ""
        if output["censorship"] is not None:
            final_output["censorship"] = output["censorship"]
        if output["guard"] is not None:
            final_output["guard"] = output["guard"]
        final_output["creator"] = output["creator"]
        final_output["public"] = output["public"]
        final_output["level"] = user.level
        final_output["default_prompt"] = output["default_prompt"]
        final_output["users"] = [u["username"] for u in output["users"]]
        final_output["options"] = output["options"]

        if project.model.type == "rag":
            if project.vector is not None:
                chunks = project.vector.info()
                if chunks is not None:
                    final_output["chunks"] = chunks
            else:
                final_output["chunks"] = 0
            final_output["embeddings"] = output["embeddings"]
            final_output["vectorstore"] = output["vectorstore"]
            final_output["system"] = output["system"] or ""


        if project.model.type == "inference":
            final_output["system"] = output["system"] or ""

        if project.model.type == "agent":
            final_output["system"] = output["system"] or ""

        if project.model.type == "ragsql":
            final_output["system"] = output["system"] or ""

        if project.model.type == "router":
            final_output["entrances"] = output["entrances"]

        if llm_model:
            final_output["llm_type"] = llm_model.props.type
            final_output["llm_privacy"] = llm_model.props.privacy
            
        del project

        return final_output
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/projects/{projectID}")
async def route_delete_project(
    request: Request,
    projectID: int,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        proj = get_project(projectID, db_wrapper, request.app.state.brain)
        proj.delete()
        
        db_wrapper.db.query(OutputDatabase).filter(
            OutputDatabase.project_id == proj.model.id
        ).delete()

        db_wrapper.delete_project(db_wrapper.get_project_by_id(projectID))

        return {"project": projectID}

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/projects/{projectID}")
async def route_edit_project(
    request: Request,
    projectID: int,
    projectModelUpdate: ProjectModelUpdate,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    if (
        projectModelUpdate.llm
        and request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper) is None
    ):
        raise HTTPException(status_code=404, detail="LLM not found")

    if user.is_private:
        llm_model = request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper)
        if llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403, detail="User not allowed to use public models"
            )

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


@router.post("/projects")
async def route_create_project(
    request: Request,
    projectModel: ProjectModelCreate,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    projectModel.name = unidecode(projectModel.name.strip().lower().replace(" ", "_"))
    projectModel.name = re.sub(r"[^\w\-.]+", "", projectModel.name)

    if projectModel.human_name is None:
        projectModel.human_name = projectModel.name

    if projectModel.type not in [
        "rag",
        "inference",
        "router",
        "ragsql",
        "vision",
        "agent",
    ]:
        raise HTTPException(status_code=404, detail="Invalid project type")

    if projectModel.name.strip() == "":
        raise HTTPException(status_code=400, detail="Invalid project name")

    if config.RESTAI_DEMO == True and not user.is_admin:
        if projectModel.type == "ragsql" or projectModel.type == "agent":
            raise HTTPException(
                status_code=403,
                detail="Demo mode, not allowed to create this type of projects.",
            )

    if (
        projectModel.type == "rag"
        and request.app.state.brain.get_embedding(projectModel.embeddings, db_wrapper)
        is None
    ):
        raise HTTPException(status_code=404, detail="Embeddings not found")
    if request.app.state.brain.get_llm(projectModel.llm, db_wrapper) is None:
        raise HTTPException(status_code=404, detail="LLM not found")

    proj = request.app.state.brain.find_project(projectModel.name, db_wrapper)
    if proj is not None:
        raise HTTPException(status_code=403, detail="Project already exists")

    if user.is_private:
        llm_model = request.app.state.brain.get_llm(projectModel.llm, db_wrapper)
        if llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403, detail="User allowed to private models only"
            )

        if projectModel.type == "rag":
            _, _, embedding_privacy, _, _ = EMBEDDINGS[projectModel.embeddings]
            if embedding_privacy != "private":
                raise HTTPException(
                    status_code=403, detail="User allowed to private models only"
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
        )
        project = get_project(project_db.id, db_wrapper, request.app.state.brain)

        if project.model.vectorstore:
            project.vector = tools.find_vector_db(project)(
                request.app.state.brain,
                project,
                request.app.state.brain.get_embedding(
                    project.model.embeddings, db_wrapper
                ),
            )

        user_db = db_wrapper.get_user_by_id(user.id)
        user_db.projects.append(project_db)
        db_wrapper.db.commit()
        return {"project": project.model.id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/embeddings/reset")
async def reset_embeddings(
    request: Request,
    projectID: int,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        project.vector.reset(request.app.state.brain)

        return {"project": project.model.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/embeddings/search")
async def find_embedding(
    request: Request,
    projectID: int,
    embedding: FindModel,
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        output = []

        if embedding.text:
            k = embedding.k or project.model.k or 2

            if embedding.score is not None:
                threshold = embedding.score
            else:
                threshold = embedding.score or project.model.score or 0.2

            retriever = VectorIndexRetriever(
                index=project.vector.index,
                similarity_top_k=k,
            )

            query_engine = RetrieverQueryEngine.from_args(
                retriever=retriever,
                node_postprocessors=[
                    SimilarityPostprocessor(similarity_cutoff=threshold)
                ],
                response_mode=ResponseMode.NO_TEXT,
            )

            response = query_engine.query(embedding.text)

            for node in response.source_nodes:
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


@router.get("/projects/{projectID}/embeddings/source/{source}")
async def get_embedding(
    request: Request,
    projectID: int,
    source: str,
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
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


@router.get("/projects/{projectID}/embeddings/id/{embedding_id}")
async def get_embedding(
    request: Request,
    projectID: int,
    embedding_id: str,
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
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


@router.post(
    "/projects/{projectID}/embeddings/ingest/text", response_model=IngestResponse
)
async def ingest_text(
    request: Request,
    projectID: int,
    ingest: TextIngestModel,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
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
    "/projects/{projectID}/embeddings/ingest/url", response_model=IngestResponse
)
async def ingest_url(
    request: Request,
    projectID: int,
    ingest: URLIngestModel,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
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

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        urls = project.vector.list()
        if ingest.url in urls:
            raise Exception("URL already ingested. Delete first.")

        loader = SeleniumWebReader()

        documents = loader.load_data(urls=[ingest.url])
        documents = extract_keywords_for_metadata(documents)

        n_chunks = index_documents_classic(
            project, documents, ingest.splitter, ingest.chunks
        )
        project.vector.save()

        return {"source": ingest.url, "documents": len(documents), "chunks": n_chunks}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/projects/{projectID}/embeddings/ingest/upload", response_model=IngestResponse
)
async def ingest_file(
    request: Request,
    projectID: int,
    file: UploadFile,
    options: str = Form("{}"),
    chunks: int = Form(256),
    splitter: str = Form("sentence"),
    classic: bool = Form(False),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    project = get_project(projectID, db_wrapper, request.app.state.brain)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects."
        )

    opts = json.loads(options)

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


@router.get("/projects/{projectID}/embeddings")
async def get_embeddings(
    request: Request,
    projectID: int,
    _: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
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


@router.delete("/projects/{projectID}/embeddings/{source}")
async def delete_embedding(
    request: Request,
    projectID: int,
    source: str,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        project = get_project(projectID, db_wrapper, request.app.state.brain)

        if project.model.type != "rag":
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


@router.post("/projects/{projectID}/chat")
async def chat_query(
    request: Request,
    projectID: int,
    q_input: ChatModel,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        if not q_input.question:
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
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{projectID}/question")
async def question_query_endpoint(
    request: Request,
    projectID: int,
    q_input: QuestionModel,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username_project_public),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        if not q_input.question:
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
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
      

@router.get("/projects/{projectID}/logs")
async def get_token_consumption(
    projectID: int,
    start: int = 0,
    end: int = 10,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
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
        return {
            "logs": logs
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
      

@router.get("/projects/{projectID}/tokens/daily")
async def get_monthly_token_consumption(
    projectID: int,
    year: int = None,
    month: int = None,
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
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
                {"date": tc.date, "input_tokens": tc.input_tokens, "output_tokens": tc.output_tokens,
                    "input_cost": tc.input_cost, "output_cost": tc.output_cost}
                for tc in token_consumptions
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
