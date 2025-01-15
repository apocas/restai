import base64
import json
import logging
import os
import re
import traceback
import urllib.parse
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, BackgroundTasks, Query
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document
from unidecode import unidecode
from app import config
from app.auth import get_current_username, get_current_username_project, get_current_username_project_public, get_team, user_is_admin_team
from app.database import get_db_wrapper, DBWrapper
from app.helper import chat_main, question_main
from app.loaders.url import SeleniumWebReader
from app.models.models import FindModel, IngestResponse, ProjectModel, ProjectModelUpdate, ProjectsResponse, \
    QuestionModel, ChatModel, Team, TextIngestModel, URLIngestModel, User
from app.project import Project
from app.vectordb import tools
from app.vectordb.tools import find_file_loader, extract_keywords_for_metadata, index_documents_classic, index_documents_docling
from modules.embeddings import EMBEDDINGS


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/projects", response_model=ProjectsResponse)
async def route_get_projects(_: Request,
                             user: User = Depends(get_current_username),
                             team: Team = Depends(get_team),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    projects = []
    ids = []
    if user.superadmin:
        projects = db_wrapper.get_projects()
    else:
        if user_is_admin_team(team.id, user):
            for project in db_wrapper.get_projects():
                if project.team_id == team.id:
                    projects.append(project)
                    ids.append(project.id)
        else:
            for project in user.projects:
                for p in db_wrapper.get_projects():
                    if project.name == p.name:
                        projects.append(p)

    return {"projects": projects}
  
@router.get("/library", response_model=ProjectsResponse)
async def route_get_library(_: Request,
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    projects = []
    for project in db_wrapper.get_projects_public():
        if project.public:
            projects.append(project)

    return {"projects": projects}


@router.get("/projects/{projectName}")
async def route_get_project(request: Request,
                            projectName: str,
                            user: User = Depends(get_current_username_project_public),
                            db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        project = request.app.state.brain.find_project(projectName, db_wrapper)

        if project is None:
            raise HTTPException(
                status_code=404, detail='Project not found')

        output = project.model.model_dump()
        final_output = {}

        try:
            llm_model = request.app.state.brain.get_llm(project.model.llm, db_wrapper)
        except Exception:
            llm_model = None

        final_output["name"] = output["name"]
        final_output["type"] = output["type"]
        final_output["llm"] = output["llm"]
        final_output["human_name"] = output["human_name"]
        final_output["human_description"] = output["human_description"] or ""
        final_output["censorship"] = output["censorship"]
        final_output["guard"] = output["guard"]
        final_output["creator"] = output["creator"]
        final_output["public"] = output["public"]
        final_output["level"] = user.level
        final_output["default_prompt"] = output["default_prompt"]

        if project.model.type == "rag":
            if project.vector is not None:
                chunks = project.vector.info()
                if chunks is not None:
                    final_output["chunks"] = chunks
            else:
                final_output["chunks"] = 0
            final_output["embeddings"] = output["embeddings"]
            final_output["k"] = output["k"]
            final_output["score"] = output["score"]
            final_output["vectorstore"] = output["vectorstore"]
            final_output["system"] = output["system"] or ""
            final_output["llm_rerank"] = output["llm_rerank"]
            final_output["colbert_rerank"] = output["colbert_rerank"]
            final_output["cache"] = output["cache"]
            final_output["cache_threshold"] = output["cache_threshold"]

        if project.model.type == "inference":
            final_output["system"] = output["system"] or ""

        if project.model.type == "agent":
            final_output["system"] = output["system"] or ""
            final_output["tools"] = output["tools"]

        if project.model.type == "ragsql":
            final_output["system"] = output["system"] or ""
            final_output["tables"] = output["tables"]
            if output["connection"] is not None:
                final_output["connection"] = re.sub(
                    r'(?<=://).+?(?=@)', "xxxx:xxxx", output["connection"])

        if project.model.type == "router":
            final_output["entrances"] = output["entrances"]

        if llm_model:
            final_output["llm_type"] = llm_model.props.type
            final_output["llm_privacy"] = llm_model.props.privacy

        final_output["team_id"] = project.model.team.id

        return final_output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.delete("/projects/{projectName}")
async def route_delete_project(request: Request,
                               projectName: str,
                               _: User = Depends(get_current_username_project),
                               db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        proj = request.app.state.brain.find_project(projectName, db_wrapper)

        if proj is not None:
            db_wrapper.delete_project(db_wrapper.get_project_by_name(projectName))
            proj.delete()
        else:
            raise HTTPException(
                status_code=404, detail='Project not found')

        return {"project": projectName}

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.patch("/projects/{projectName}")
async def route_edit_project(request: Request,
                             projectName: str,
                             projectModelUpdate: ProjectModelUpdate,
                             user: User = Depends(get_current_username_project),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    if projectModelUpdate.llm and request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper) is None:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    if user.is_private:
        llm_model = request.app.state.brain.get_llm(projectModelUpdate.llm, db_wrapper)
        if llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User not allowed to use public models')

    try:
        if db_wrapper.edit_project(projectName, projectModelUpdate):
            return {"project": projectName}
        else:
            raise HTTPException(
                status_code=404, detail='Project not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects")
async def route_create_project(request: Request,
                               projectModel: ProjectModel,
                               user: User = Depends(get_current_username),
                               db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    projectModel.human_name = projectModel.name.strip()
    projectModel.name = unidecode(
        projectModel.name.strip().lower().replace(" ", "_"))
    projectModel.name = re.sub(r'[^\w\-.]+', '', projectModel.name)

    if projectModel.type not in ["rag", "inference", "router", "ragsql", "vision", "agent"]:
        raise HTTPException(
            status_code=404,
            detail='Invalid project type')

    if projectModel.name.strip() == "":
        raise HTTPException(
            status_code=400,
            detail='Invalid project name')

    if config.RESTAI_DEMO and not user.superadmin:
        if projectModel.type == "ragsql" or projectModel.type == "agent":
            raise HTTPException(
                status_code=403,
                detail='Demo mode, not allowed to create this type of projects.')

    if projectModel.type == "rag" and request.app.state.brain.get_embedding(projectModel.embeddings, db_wrapper) is None:
        raise HTTPException(
            status_code=404,
            detail='Embeddings not found')
    if request.app.state.brain.get_llm(projectModel.llm, db_wrapper) is None:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    proj = request.app.state.brain.find_project(projectModel.name, db_wrapper)
    if proj is not None:
        raise HTTPException(
            status_code=403,
            detail='Project already exists')

    if user.is_private:
        llm_model = request.app.state.brain.get_llm(projectModel.llm, db_wrapper)
        if llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User allowed to private models only')

        if projectModel.type == "rag":
            _, _, embedding_privacy, _, _ = EMBEDDINGS[
                projectModel.embeddings]
            if embedding_privacy != "private":
                raise HTTPException(
                    status_code=403,
                    detail='User allowed to private models only')

    try:
        db_wrapper.create_project(
            projectModel.name,
            projectModel.embeddings,
            projectModel.llm,
            projectModel.vectorstore,
            projectModel.human_name,
            projectModel.type,
            user.id
        )
        project = Project(projectModel)

        if project.model.vectorstore:
            project.vector = tools.find_vector_db(project)(request.app.state.brain, project, request.app.state.brain.get_embedding(project.model.embeddings, db_wrapper))

        project_db = db_wrapper.get_project_by_name(project.model.name)

        user_db = db_wrapper.get_user_by_id(user.id)
        user_db.projects.append(project_db)
        db_wrapper.db.commit()
        return {"project": projectModel.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects/{projectName}/embeddings/reset")
async def reset_embeddings(
        request: Request,
        projectName: str,
        _: User = Depends(get_current_username_project),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        project = request.app.state.brain.find_project(projectName, db_wrapper)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects.")

        project.vector.reset(request.app.state.brain)

        return {"project": project.model.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.post("/projects/{projectName}/clone/{newProjectName}")
async def clone_project(request: Request, projectName: str, newProjectName: str,
                        _: User = Depends(get_current_username_project),
                        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    project = request.app.state.brain.find_project(projectName, db_wrapper)
    if project is None:
        raise HTTPException(
            status_code=404, detail='Project not found')

    newProject = db_wrapper.get_project_by_name(newProjectName)
    if newProject is not None:
        raise HTTPException(
            status_code=403, detail='Project already exists')

    project_db = db_wrapper.get_project_by_name(projectName)

    newProject_db = db_wrapper.create_project(
        newProjectName,
        project.model.embeddings,
        project.model.llm,
        project.model.vectorstore,
        project.model.type
    )

    newProject_db.system = project.model.system
    newProject_db.censorship = project.model.censorship
    newProject_db.k = project.model.k
    newProject_db.score = project.model.score
    newProject_db.llm_rerank = project.model.llm_rerank
    newProject_db.colbert_rerank = project.model.colbert_rerank
    newProject_db.cache = project.model.cache
    newProject_db.cache_threshold = project.model.cache_threshold
    newProject_db.guard = project.model.guard
    newProject_db.human_name = project.model.human_name
    newProject_db.human_description = project.model.human_description
    newProject_db.tables = project.model.tables
    newProject_db.connection = project.model.connection

    for user in project_db.users:
        newProject_db.users.append(user)

    for entrance in project_db.entrances:
        newProject_db.entrances.append(entrance)

    db_wrapper.db.commit()

    return {"project": newProjectName}


@router.post("/projects/{projectName}/embeddings/search")
async def find_embedding(request: Request, projectName: str, embedding: FindModel,
                         _: User = Depends(get_current_username_project_public),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    project = request.app.state.brain.find_project(projectName, db_wrapper)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects.")

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
            node_postprocessors=[SimilarityPostprocessor(
                similarity_cutoff=threshold)],
            response_mode=ResponseMode.NO_TEXT
        )

        response = query_engine.query(embedding.text)

        for node in response.source_nodes:
            output.append(
                {"source": node.metadata["source"], "score": node.score, "id": node.node_id})

    elif embedding.source:
        output = project.vector.list_source(embedding.source)

    return {"embeddings": output}


@router.get("/projects/{projectName}/embeddings/source/{source}")
async def get_embedding(request: Request, projectName: str, source: str,
                        _: User = Depends(get_current_username_project_public),
                        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    project = request.app.state.brain.find_project(projectName, db_wrapper)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects.")

    docs = project.vector.find_source(base64.b64decode(source).decode('utf-8'))

    if len(docs['ids']) == 0:
        return {"ids": []}
    else:
        return docs


@router.get("/projects/{projectName}/embeddings/id/{embedding_id}")
async def get_embedding(request: Request, projectName: str,
                        embedding_id: str,
                        _: User = Depends(get_current_username_project_public),
                        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    project = request.app.state.brain.find_project(projectName, db_wrapper)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects.")

    chunk = project.vector.find_id(embedding_id)
    return chunk


@router.post("/projects/{projectName}/embeddings/ingest/text", response_model=IngestResponse)
async def ingest_text(request: Request, projectName: str, ingest: TextIngestModel,
                      _: User = Depends(get_current_username_project),
                      db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        project = request.app.state.brain.find_project(projectName, db_wrapper)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects.")

        metadata = {"source": ingest.source}
        documents = [Document(text=ingest.text, metadata=metadata)]

        if ingest.keywords and len(ingest.keywords) > 0:
            for document in documents:
                document.metadata["keywords"] = ", ".join(ingest.keywords)
        else:
            documents = extract_keywords_for_metadata(documents)

        # for document in documents:
        #    document.text = document.text.decode('utf-8')

        n_chunks = index_documents_classic(project, documents, ingest.splitter, ingest.chunks)
        project.vector.save()

        return {"source": ingest.source, "documents": len(documents), "chunks": n_chunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects/{projectName}/embeddings/ingest/url", response_model=IngestResponse)
async def ingest_url(request: Request, projectName: str, ingest: URLIngestModel,
                     user: User = Depends(get_current_username_project),
                     db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    if config.RESTAI_DEMO and not user.superadmin:
        raise HTTPException(
                status_code=403,
                detail='Demo mode, not allowed to ingest from an URL.')
    
    try:
        if ingest.url and not ingest.url.startswith('http'):
            raise HTTPException(
                status_code=400, detail="Specify the protocol http:// or https://")

        project = request.app.state.brain.find_project(projectName, db_wrapper)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects.")

        urls = project.vector.list()
        if ingest.url in urls:
            raise Exception("URL already ingested. Delete first.")

        loader = SeleniumWebReader()

        documents = loader.load_data(urls=[ingest.url])
        documents = extract_keywords_for_metadata(documents)

        n_chunks = index_documents_classic(project, documents, ingest.splitter, ingest.chunks)
        project.vector.save()

        return {"source": ingest.url, "documents": len(documents), "chunks": n_chunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects/{projectName}/embeddings/ingest/upload", response_model=IngestResponse)
async def ingest_file(
        request: Request,
        projectName: str,
        file: UploadFile,
        options: str = Form("{}"),
        chunks: int = Form(256),
        splitter: str = Form("sentence"),
        classic: bool = Form(False),
        _: User = Depends(get_current_username_project),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
    from llama_index.readers.docling import DoclingReader
    
    
    project = request.app.state.brain.find_project(projectName, db_wrapper)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects.")

    _, ext = os.path.splitext(file.filename or '')
    temp = NamedTemporaryFile(delete=False, suffix=ext)
    try:
        contents = file.file.read()
        with temp as f:
            f.write(contents)
    except Exception:
        raise HTTPException(
            status_code=500, detail="Error while saving file.")
    finally:
        file.file.close()

    opts = json.loads(urllib.parse.unquote(options))
    
    if classic == True:
        loader = find_file_loader(ext, opts)
        
        try:
            documents = loader.load_data(file=Path(temp.name))
        except TypeError as e:
            documents = loader.load_data(input_file=Path(temp.name))
        except Exception as e:
            logging.error(e)
            traceback.print_tb(e.__traceback__)

            raise HTTPException(
                status_code=500, detail="Error while loading file.")
        
    else:
        try:
            reader = DoclingReader()
            documents = reader.load_data(file_path=Path(temp.name))
        except Exception as e:
            if "File format not allowed" in str(e):
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file format. Retry in classic mode."
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
            "documents": len(documents), "chunks": n_chunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)

        raise HTTPException(
            status_code=500, detail="Error while indexing data.")


@router.get('/projects/{projectName}/embeddings')
async def get_embeddings(
        request: Request,
        projectName: str,
        _: User = Depends(get_current_username_project_public),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    project = request.app.state.brain.find_project(projectName, db_wrapper)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects.")

    if project.vector is not None:
        output = project.vector.list()
    else:
        output = []

    return {"embeddings": output}


@router.delete('/projects/{projectName}/embeddings/{source}')
async def delete_embedding(
        request: Request,
        projectName: str,
        source: str,
        _: User = Depends(get_current_username_project),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    project = request.app.state.brain.find_project(projectName, db_wrapper)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail="Only available for RAG projects.")

    ids = project.vector.delete_source(base64.b64decode(source).decode('utf-8'))

    return {"deleted": len(ids)}


@router.post("/projects/{projectName}/chat")
async def chat_query(
        request: Request,
        projectName: str,
        q_input: ChatModel,
        background_tasks: BackgroundTasks,
        user: User = Depends(get_current_username_project_public),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        if not q_input.question:
            raise HTTPException(
                status_code=400, detail="Missing question")

        project = request.app.state.brain.find_project(projectName, db_wrapper)
        if project is None:
            raise Exception("Project not found")

        return await chat_main(request, request.app.state.brain, project, q_input, user, db_wrapper, background_tasks)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects/{projectName}/question")
async def question_query_endpoint(
        request: Request,
        projectName: str,
        q_input: QuestionModel,
        background_tasks: BackgroundTasks,
        user: User = Depends(get_current_username_project_public),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        if not q_input.question:
            raise HTTPException(
                status_code=400, detail="Question missing")

        project = request.app.state.brain.find_project(projectName, db_wrapper)
        if project is None:
            raise Exception("Project not found")

        if user.level == "public":
            q_input = QuestionModel(question=q_input.question, image=q_input.image, negative=q_input.negative)

        return await question_main(request, request.app.state.brain, project, q_input, user, db_wrapper, background_tasks)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))
