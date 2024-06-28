from fastapi import APIRouter
import os
from starlette.requests import Request
from unidecode import unidecode
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
import urllib.parse
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import Document
from llama_index.core.retrievers import VectorIndexRetriever
from fastapi import Form, HTTPException, Request, UploadFile, BackgroundTasks
import traceback
from tempfile import NamedTemporaryFile
import re
from pathlib import Path
import logging
import json
import base64
from app import config

from app.helper import chat_main, question_main
from app.vectordb import tools
from app.project import Project
from modules.embeddings import EMBEDDINGS
from app.models.models import FindModel, IngestResponse,ProjectModel, ProjectModelUpdate, ProjectsResponse, QuestionModel, ChatModel, TextIngestModel, URLIngestModel, User
from app.loaders.url import SeleniumWebReader
from app.database import dbc, get_db
from app.auth import get_current_username, get_current_username_project, get_current_username_project_public
from app.vectordb.tools import FindFileLoader, IndexDocuments, ExtractKeywordsForMetadata


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()

@router.get("/projects", response_model=ProjectsResponse)
async def get_projects(request: Request, filter: str = "own", user: User = Depends(get_current_username), db: Session = Depends(get_db)):
    projects = []     
    if filter == "own":
        if user.is_admin:
            projects = dbc.get_projects(db)
        else:
            for project in user.projects:
                for p in dbc.get_projects(db):
                    if project.name == p.name:
                        projects.append(p)
    elif filter == "public":
        for project in dbc.get_projects(db):
            if project.public == True:
                projects.append(project)

    for project in projects:
        try:
            model = request.app.state.brain.getLLM(project.llm, db)
            project.llm_type = model.props.type
            project.llm_privacy = model.props.privacy
        except Exception as e:
            project.llm_type = "unknown"
            project.llm_privacy = "unknown"

    return {"projects": projects}


@router.get("/projects/{projectName}")
async def get_project(request: Request, projectName: str, user: User = Depends(get_current_username_project_public), db: Session = Depends(get_db)):
    try:
        project = request.app.state.brain.findProject(projectName, db)
        
        if project is None:
            raise HTTPException(
                status_code=404, detail='Project not found')

        output = project.model.model_dump()
        final_output = {}
        
        try:
            llm_model = request.app.state.brain.getLLM(project.model.llm, db)
        except Exception as e:
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
            final_output["llm_type"]=llm_model.props.type
            final_output["llm_privacy"]=llm_model.props.privacy

        return final_output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.delete("/projects/{projectName}")
async def delete_project(request: Request, projectName: str, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    try:
        proj = request.app.state.brain.findProject(projectName, db)
        
        if proj is not None:
            dbc.delete_project(db, dbc.get_project_by_name(db, projectName))
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
async def edit_project(request: Request, projectName: str, projectModelUpdate: ProjectModelUpdate, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
  
    if projectModelUpdate.llm and request.app.state.brain.getLLM(projectModelUpdate.llm, db) is None:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    if user.is_private:
        llm_model = request.app.state.brain.getLLM(projectModelUpdate.llm, db)
        if llm_model.props.privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User not allowed to use public models')

    try:
        if dbc.editProject(projectName, projectModelUpdate, db):
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
async def create_project(request: Request, projectModel: ProjectModel, user: User = Depends(get_current_username), db: Session = Depends(get_db)):
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
        
    if config.RESTAI_DEMO:
        if projectModel.type == "ragsql":
            raise HTTPException(
                status_code=403,
                detail='Demo mode, not allowed to create RAGSQL projects')

    if projectModel.type == "rag" and projectModel.embeddings not in EMBEDDINGS:
        raise HTTPException(
            status_code=404,
            detail='Embeddings not found')
    if request.app.state.brain.getLLM(projectModel.llm, db) is None:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    proj = request.app.state.brain.findProject(projectModel.name, db)
    if proj is not None:
        raise HTTPException(
            status_code=403,
            detail='Project already exists')

    if user.is_private:
        llm_model = request.app.state.brain.getLLM(projectModel.llm, db)
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
        dbc.create_project(
            db,
            projectModel.name,
            projectModel.embeddings,
            projectModel.llm,
            projectModel.vectorstore,
            projectModel.human_name,
            projectModel.type,
            user.id
        )
        project = Project(projectModel)
        
        if(project.model.vectorstore):
            project.vector = tools.findVectorDB(project)(request.app.state.brain, project)
        
        projectdb = dbc.get_project_by_name(db, project.model.name)
        
        userdb = dbc.get_user_by_id(db, user.id)
        userdb.projects.append(projectdb)
        db.commit()
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
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = request.app.state.brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        project.vector.reset(request.app.state.brain)

        return {"project": project.model.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))

@router.post("/projects/{projectName}/clone/{newProjectName}")
async def clone_project(request: Request, projectName: str, newProjectName: str,
                         user: User = Depends(get_current_username_project),
                         db: Session = Depends(get_db)):
    project = request.app.state.brain.findProject(projectName, db)
    if project is None:
        raise HTTPException(
            status_code=404, detail='Project not found')
        
    newProject = dbc.get_project_by_name(db, newProjectName)
    if newProject is not None:
        raise HTTPException(
            status_code=403, detail='Project already exists')
        
    project_db = dbc.get_project_by_name(db, projectName)
    
    newProject_db = dbc.create_project(
        db,
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
        
    db.commit()

    return {"project": newProjectName}

@router.post("/projects/{projectName}/embeddings/search")
async def find_embedding(request: Request, projectName: str, embedding: FindModel,
                         user: User = Depends(get_current_username_project_public),
                         db: Session = Depends(get_db)):
    project = request.app.state.brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    output = []

    if (embedding.text):
        k = embedding.k or project.model.k or 2

        if (embedding.score != None):
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
            response_mode="no_text"
        )

        response = query_engine.query(embedding.text)

        for node in response.source_nodes:
            output.append(
                {"source": node.metadata["source"], "score": node.score, "id": node.node_id})

    elif (embedding.source):
        output = project.vector.list_source(embedding.source)

    return {"embeddings": output}


@router.get("/projects/{projectName}/embeddings/source/{source}")
async def get_embedding(request: Request, projectName: str, source: str,
                        user: User = Depends(get_current_username_project_public),
                        db: Session = Depends(get_db)):
    project = request.app.state.brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    docs = project.vector.find_source(base64.b64decode(source).decode('utf-8'))

    if (len(docs['ids']) == 0):
        return {"ids": []}
    else:
        return docs


@router.get("/projects/{projectName}/embeddings/id/{id}")
async def get_embedding(request: Request, projectName: str, id: str,
                        user: User = Depends(get_current_username_project_public),
                        db: Session = Depends(get_db)):
    project = request.app.state.brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    chunk = project.vector.find_id(id)
    return chunk


@router.post("/projects/{projectName}/embeddings/ingest/text", response_model=IngestResponse)
async def ingest_text(request: Request, projectName: str, ingest: TextIngestModel,
                      user: User = Depends(get_current_username_project),
                      db: Session = Depends(get_db)):

    try:
        project = request.app.state.brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        metadata = {"source": ingest.source}
        documents = [Document(text=ingest.text, metadata=metadata)]

        if ingest.keywords and len(ingest.keywords) > 0:
            for document in documents:
                document.metadata["keywords"] = ", ".join(ingest.keywords)
        else:
            documents = ExtractKeywordsForMetadata(documents)

        # for document in documents:
        #    document.text = document.text.decode('utf-8')

        nchunks = IndexDocuments(project, documents, ingest.splitter, ingest.chunks)
        project.vector.save()

        return {"source": ingest.source, "documents": len(documents), "chunks": nchunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects/{projectName}/embeddings/ingest/url", response_model=IngestResponse)
async def ingest_url(request: Request, projectName: str, ingest: URLIngestModel,
                     user: User = Depends(get_current_username_project),
                     db: Session = Depends(get_db)):
    try:
        if ingest.url and not ingest.url.startswith('http'):
            raise HTTPException(
                status_code=400, detail='{"error": "Specify the protocol http:// or https://"}')
      
        project = request.app.state.brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        urls = project.vector.list()
        if (ingest.url in urls):
            raise Exception("URL already ingested. Delete first.")

        loader = SeleniumWebReader()

        documents = loader.load_data(urls=[ingest.url])
        documents = ExtractKeywordsForMetadata(documents)

        nchunks = IndexDocuments(project, documents, ingest.splitter, ingest.chunks)
        project.vector.save()

        return {"source": ingest.url, "documents": len(documents), "chunks": nchunks}
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
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = request.app.state.brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        _, ext = os.path.splitext(file.filename or '')
        temp = NamedTemporaryFile(delete=False, suffix=ext)
        try:
            contents = file.file.read()
            with temp as f:
                f.write(contents)
        except Exception:
            raise HTTPException(
                status_code=500, detail='{"error": "Error while saving file."}')
        finally:
            file.file.close()

        opts = json.loads(urllib.parse.unquote(options))

        loader = FindFileLoader(ext, opts)
        documents = loader.load_data(file=Path(temp.name))

        for document in documents:
            if "filename" in document.metadata:
                del document.metadata["filename"]
            document.metadata["source"] = file.filename

        documents = ExtractKeywordsForMetadata(documents)

        nchunks = IndexDocuments(project, documents, splitter, chunks)
        project.vector.save()

        return {
            "source": file.filename,
            "documents": len(documents), "chunks": nchunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)

        raise HTTPException(
            status_code=500, detail=str(e))


@router.get('/projects/{projectName}/embeddings')
async def get_embeddings(
        request: Request,
        projectName: str,
        user: User = Depends(get_current_username_project_public),
        db: Session = Depends(get_db)):
    project = request.app.state.brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

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
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    project = request.app.state.brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    ids = project.vector.delete_source(base64.b64decode(source).decode('utf-8'))

    return {"deleted": len(ids)}


@router.post("/projects/{projectName}/chat")
async def chat_query(
        request: Request,
        projectName: str,
        input: ChatModel,
        background_tasks: BackgroundTasks,
        user: User = Depends(get_current_username_project_public),
        db: Session = Depends(get_db)):
    try:
        if not input.question:
            raise HTTPException(
                status_code=400, detail='{"error": "Missing question"}')
      
        project = request.app.state.brain.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")

        return await chat_main(request, request.app.state.brain, project, input, user, db, background_tasks)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.post("/projects/{projectName}/question")
async def question_query_endpoint(
        request: Request,
        projectName: str,
        input: QuestionModel,
        background_tasks: BackgroundTasks,
        user: User = Depends(get_current_username_project_public),
        db: Session = Depends(get_db)):
    try:
        if not input.question:
            raise HTTPException(
                status_code=400, detail='{"error": "Missing question"}')
            
        project = request.app.state.brain.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")
          
        if user.level == "public":
            input = QuestionModel(question=input.question, image=input.image, negative=input.negative)
            
        return await question_main(request, request.app.state.brain, project, input, user, db, background_tasks)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))