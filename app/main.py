import base64
import json
import logging
import os
import re
import shutil
from tempfile import NamedTemporaryFile
import traceback
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from langchain.document_loaders import (
    WebBaseLoader,
    SeleniumURLLoader,
    RecursiveUrlLoader
)
from bs4 import BeautifulSoup as Soup
from dotenv import load_dotenv
import requests
from app.auth import get_current_username, get_current_username_admin, get_current_username_project, get_current_username_user
from app.brain import Brain
from app.database import Database, dbc, get_db
from app.databasemodels import UserDatabase
import urllib.parse

from app.models import ChatResponse, FindModel, HardwareInfo, ProjectInfo, ProjectModel, ProjectModelUpdate, QuestionModel, ChatModel, QuestionResponse, TextIngestModel, URLIngestModel, User, UserCreate, UserUpdate, VisionModel
from app.tools import FindFileLoader, IndexDocuments, ExtractKeywordsForMetadata, get_logger, loadEnvVars
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.vectordb import vector_delete_source, vector_delete_id, vector_find, vector_info, vector_init, vector_list_source, vector_reset, vector_save, vector_list
from langchain_core.documents import Document

from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS
from modules.loaders import LOADERS
import logging
import psutil
import GPUtil

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session


load_dotenv()
loadEnvVars()

logging.basicConfig(level=os.environ["LOG_LEVEL"])

app = FastAPI(
    title="RestAI",
    description="Modular REST API bootstrap on top of LangChain. Create embeddings associated with a project tenant and interact using a LLM. RAG as a service.",
    version="3.3.0",
    contact={
        "name": "Pedro Dias",
        "url": "https://github.com/apocas/restai",
        "email": "petermdias@gmail.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

if "RESTAI_DEV" in os.environ:
    print("Running in development mode!")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

brain = Brain()
logs_inference = get_logger("inference")


@app.get("/")
async def get(request: Request):
    return "RESTAI, so many 'A's and 'I's, so little time..."


@app.get("/info")
async def get_info(user: User = Depends(get_current_username)):
    output = {
        "version": app.version,
        "loaders": list(LOADERS.keys()),
        "embeddings": [],
        "llms": []
    }

    for llm in LLMS:
        llm_class, llm_args, prompt, privacy, description, typel = LLMS[llm]
        output["llms"].append({
            "name": llm,
            "prompt": prompt,
            "privacy": privacy,
            "description": description,
            "type": typel
        })

    for embedding in EMBEDDINGS:
        embedding_class, embedding_args, privacy, description = EMBEDDINGS[embedding]
        output["embeddings"].append({
            "name": embedding,
            "privacy": privacy,
            "description": description
        })
    return output


@app.get("/users/{username}", response_model=User)
async def get_user(username: str, user: User = Depends(get_current_username_user), db: Session = Depends(get_db)):
    try:
        return User.model_validate(dbc.get_user_by_username(db, username))
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.get("/users", response_model=list[User])
def read_users(
        user: User = Depends(get_current_username_admin),
        db: Session = Depends(get_db)):
    users = dbc.get_users(db)
    return users


@app.post("/users", response_model=User)
def create_user(userc: UserCreate,
                user: User = Depends(get_current_username_admin),
                db: Session = Depends(get_db)):
    try:
        user = dbc.create_user(db,
                               userc.username,
                               userc.password,
                               userc.is_admin,
                               userc.is_private)
        return user
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail='Failed to create user ' + userc.username)


@app.patch("/users/{username}", response_model=User)
def update_user(
        username: str,
        userc: UserUpdate,
        user: User = Depends(get_current_username_user),
        db: Session = Depends(get_db)):
    try:
        useru = dbc.get_user_by_username(db, username)
        if useru is None:
            raise Exception("User not found")

        if not user.is_admin and userc.is_admin is True:
            raise Exception("Insuficient permissions")

        dbc.update_user(db, useru, userc)

        if userc.projects is not None:
            dbc.delete_userprojects(db, useru)
            for project in userc.projects:
                projectdb = dbc.get_project_by_name(db, project)
                if projectdb is None:
                    raise Exception("Project not found")
                dbc.add_userproject(db, useru, project, projectdb.id)
        return useru
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.delete("/users/{username}")
def delete_user(username: str,
                user: User = Depends(get_current_username_admin),
                db: Session = Depends(get_db)):
    try:
        user = dbc.get_user_by_username(db, username)
        if user is None:
            raise Exception("User not found")
        dbc.delete_user(db, user)
        return {"deleted": username}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.get("/hardware", response_model=HardwareInfo)
def get_hardware_info(user: User = Depends(get_current_username)):
    try:
        cpu_load = psutil.cpu_percent()
        ram_usage = psutil.virtual_memory().percent

        gpu_load = None
        gpu_temp = None
        gpu_ram_usage = None

        GPUs = GPUtil.getGPUs()
        if len(GPUs) > 0:
            gpu = GPUs[0]
            gpu_load = getattr(gpu, 'load', None)
            gpu_temp = getattr(gpu, 'temperature', None)
            gpu_ram_usage = getattr(gpu, 'memoryUtil', None)

        cpu_load = int(cpu_load)
        if gpu_load is not None:
            gpu_load = int(gpu_load * 100)

        if gpu_ram_usage is not None:
            gpu_ram_usage = int(gpu_ram_usage * 100)

        return HardwareInfo(
            cpu_load=cpu_load,
            ram_usage=ram_usage,
            gpu_load=gpu_load,
            gpu_temp=gpu_temp,
            gpu_ram_usage=gpu_ram_usage,
            models_vram=brain.memoryModelsInfo()
        )
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.get("/projects", response_model=list[ProjectModel])
async def get_projects(request: Request, user: User = Depends(get_current_username), db: Session = Depends(get_db)):
    if user.is_admin:
        projects = dbc.get_projects(db)
    else:
        projects = []
        for project in user.projects:
            for p in dbc.get_projects(db):
                if project.name == p.name:
                    projects.append(p)

    for project in projects:
        llm_class, llm_args, prompt, llm_privacy, description, llm_type = LLMS[project.llm]
        project.llm_type = llm_type
        project.llm_privacy = llm_privacy

    return projects


@app.get("/projects/{projectName}", response_model=ProjectInfo)
async def get_project(projectName: str, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        llm_class, llm_args, prompt, llm_privacy, description, llm_type = LLMS[
            project.model.llm]

        docs, metas = vector_info(project)

        output = ProjectInfo(
            name=project.model.name,
            embeddings=project.model.embeddings,
            llm=project.model.llm,
            llm_type=llm_type,
            llm_privacy=llm_privacy,
            system=project.model.system,
            sandboxed=project.model.sandboxed,
            censorship=project.model.censorship,
            score=project.model.score,
            k=project.model.k,
            sandbox_project=project.model.sandbox_project,
            vectorstore=project.model.vectorstore,)
        output.documents = docs
        output.metadatas = metas

        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.delete("/projects/{projectName}")
async def delete_project(projectName: str, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    try:
        if brain.deleteProject(projectName, db):
            return {"project": projectName}
        else:
            raise HTTPException(
                status_code=404, detail='Project not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.patch("/projects/{projectName}")
async def edit_project(projectName: str, projectModelUpdate: ProjectModelUpdate, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    if projectModelUpdate is not None and projectModelUpdate.llm not in LLMS:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    if projectModelUpdate is not None and projectModelUpdate.sandbox_project is not None:
        proj = brain.findProject(projectModelUpdate.sandbox_project, db)
        if proj is None:
            raise HTTPException(
                status_code=404,
                detail='Sandbox project not found')

    if user.is_private:
        llm_class, llm_args, prompt, privacy, description, type = LLMS[projectModelUpdate.llm]
        if privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User allowed to private models only')

    try:
        if brain.editProject(projectName, projectModelUpdate, db):
            return {"project": projectName}
        else:
            raise HTTPException(
                status_code=404, detail='Project not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects")
async def create_project(projectModel: ProjectModel, user: User = Depends(get_current_username), db: Session = Depends(get_db)):

    if projectModel.embeddings not in EMBEDDINGS:
        raise HTTPException(
            status_code=404,
            detail='Embeddings not found')
    if projectModel.llm not in LLMS:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    proj = brain.findProject(projectModel.name, db)
    if proj is not None:
        raise HTTPException(
            status_code=403,
            detail='Project already exists')

    if user.is_private:
        llm_class, llm_args, prompt, privacy, description, type = LLMS[projectModel.llm]
        if privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User allowed to private models only')

        embedding_class, embedding_args, embedding_privacy, embedding_description = EMBEDDINGS[
            projectModel.embeddings]
        if embedding_privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User allowed to private models only')

    try:
        project = brain.createProject(projectModel, db)
        projectdb = dbc.get_project_by_name(db, project.model.name)
        dbc.add_userproject(db, user, projectModel.name, projectdb.id)
        return {"project": projectModel.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/embeddings/reset")
def project_reset(
        projectName: str,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        vector_reset(brain, project)

        return {"project": project.model.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.post("/projects/{projectName}/embeddings/find")
def get_embedding(projectName: str, embedding: FindModel,
                  user: User = Depends(get_current_username_project),
                  db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    output = []

    if (embedding.text):
        retriever = project.db.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "score_threshold": project.model.score or 0.2,
                "k": project.model.k or 1})

        try:
            docs = retriever.get_relevant_documents(embedding.text)
        except BaseException:
            docs = []

        for doc in docs:
            if doc.metadata["source"] not in output:
                output.append(doc.metadata["source"])

    elif (embedding.source):
        output = vector_list_source(project, embedding.source)

    return {"embeddings": output}

@app.get("/projects/{projectName}/embeddings/{source}")
def get_embedding(projectName: str, source: str,
                  user: User = Depends(get_current_username_project),
                  db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    docs = vector_find(project, base64.b64decode(source).decode('utf-8'))

    if (len(docs['ids']) == 0):
        return {"ids": []}
    else:
        return docs


@app.post("/projects/{projectName}/embeddings/ingest/text")
def ingest_url(projectName: str, ingest: TextIngestModel,
               user: User = Depends(get_current_username_project),
               db: Session = Depends(get_db)):

    try:
        project = brain.findProject(projectName, db)

        metadata = {"source": ingest.source}
        documents = [Document(page_content=ingest.text, metadata=metadata)]

        documents = ExtractKeywordsForMetadata(documents)

        ids = IndexDocuments(brain, project, documents)
        vector_save(project)

        return {"name": ingest.source, "documents": len(ids)}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/embeddings/ingest/url")
def ingest_url(projectName: str, ingest: URLIngestModel,
               user: User = Depends(get_current_username_project),
               db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        urls = vector_list(project, "url")["urls"]
        if (ingest.url in urls):
            raise Exception("URL already ingested. Delete first.")

        loader = loader = SeleniumURLLoader(urls=[ingest.url])

        documents = loader.load()
        documents = ExtractKeywordsForMetadata(documents)

        ids = IndexDocuments(brain, project, documents)
        vector_save(project)

        return {"url": ingest.url, "documents": len(ids)}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/embeddings/ingest/upload")
def ingest_file(
        projectName: str,
        file: UploadFile,
        options: str = Form("{}"),
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        temp = NamedTemporaryFile(delete=False)
        try:
            contents = file.file.read()
            with temp as f:
                f.write(contents)
        except Exception:
            raise HTTPException(
                status_code=500, detail='{"error": "Error while saving file."}')
        finally:
            file.file.close()

        _, ext = os.path.splitext(file.filename or '')

        loader = FindFileLoader(
            temp.name, ext, json.loads(
                urllib.parse.unquote(options)))
        documents = loader.load()

        for document in documents:
            document.metadata["source"] = file.filename

        documents = ExtractKeywordsForMetadata(documents)

        ids = IndexDocuments(brain, project, documents)
        vector_save(project)

        return {
            "filename": file.filename,
            "type": file.content_type,
            "documents": len(ids)}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)

        raise HTTPException(
            status_code=500, detail=str(e))


@app.get('/projects/{projectName}/embeddings')
def list_files(
        projectName: str,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    output = vector_list(project)

    return output


@app.delete('/projects/{projectName}/embeddings/{source}')
def delete_file(
        projectName: str,
        source: str,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    ids = vector_delete_source(
        project, base64.b64decode(source).decode('utf-8'))

    return {"deleted": len(ids)}


@app.post("/projects/{projectName}/vision", response_model=QuestionResponse)
def vision_project(
        projectName: str,
        input: VisionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):

    try:
        if input.image:
            url_pattern = re.compile(
                r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
            is_url = re.match(url_pattern, input.image) is not None

            if is_url:
                response = requests.get(input.image)
                response.raise_for_status()
                image_data = response.content
                input.image = base64.b64encode(image_data).decode('utf-8')

        answer, docs, image = brain.entryVision(projectName, input, db)

        output = {
            "question": input.question,
            "answer": answer,
            "image": image,
            "sources": docs,
            "type": "vision"
        }

        logs_inference.info({"user": user.username, "output": output})

        return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/question", response_model=QuestionResponse)
def question_project(
        projectName: str,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        answer, docs = brain.entryQuestion(projectName, input, db)

        sources = [{"content": doc.page_content,
                    "keywords": doc.metadata.get("keywords", ""),
                    "source": doc.metadata.get("source", "")} for doc in docs]

        output = {
            "question": input.question,
            "answer": answer,
            "sources": sources,
            "type": "question"
        }

        logs_inference.info({"user": user.username, "output": output})

        return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/chat", response_model=ChatResponse)
def chat_project(
        projectName: str,
        input: ChatModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        chat, output = brain.entryChat(projectName, input, db)

        docs = output["source_documents"]
        answer = output["answer"].strip()

        sources = [{"content": doc.page_content,
                    "keywords": doc.metadata.get("keywords", ""),
                    "source": doc.metadata.get("source", "")} for doc in docs]

        output = {
            "question": input.question,
            "answer": answer,
            "id": chat.id,
            "sources": sources,
            "type": "chat"}

        logs_inference.info({"user": user.username, "output": output})

        return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


try:
    app.mount("/admin/", StaticFiles(directory="frontend/html/",
              html=True), name="static_admin")
    app.mount(
        "/admin/static/js",
        StaticFiles(
            directory="frontend/html/static/js"),
        name="static_js")
    app.mount(
        "/admin/static/css",
        StaticFiles(
            directory="frontend/html/static/css"),
        name="static_css")
    app.mount(
        "/admin/static/media",
        StaticFiles(
            directory="frontend/html/static/media"),
        name="static_media")
except BaseException:
    print("Admin interface not available. Did you run 'make frontend'?")
