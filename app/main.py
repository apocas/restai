import base64
import logging
import os
import shutil
from tempfile import NamedTemporaryFile
import traceback
from fastapi import FastAPI, HTTPException, Request, UploadFile
from langchain.document_loaders import (
    WebBaseLoader,
    SeleniumURLLoader,
    RecursiveUrlLoader
)
from bs4 import BeautifulSoup as Soup
from dotenv import load_dotenv
from app.brain import Brain

from app.models import EmbeddingModel, IngestModel, ProjectModel, QuestionModel, ChatModel
from app.tools import FindFileLoader, IndexDocuments, ExtractKeywordsForMetadata
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS
from modules.loaders import LOADERS
import logging
import psutil
import GPUtil

load_dotenv()

if "EMBEDDINGS_PATH" not in os.environ:
    os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

if "UPLOADS_PATH" not in os.environ:
    os.environ["UPLOADS_PATH"] = "./uploads/"

if "PROJECTS_PATH" not in os.environ:
    os.environ["PROJECTS_PATH"] = "./projects/"

if "ANONYMIZED_TELEMETRY" not in os.environ:
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

if "LOG_LEVEL" not in os.environ:
    os.environ["LOG_LEVEL"] = "INFO"

os.environ["ALLOW_RESET"] = "true"

logging.basicConfig(level=os.environ["LOG_LEVEL"])

app = FastAPI(
    title="RestAI",
    description="Modular REST API bootstrap on top of LangChain. Create embeddings associated with a project tenant and interact using a LLM. RAG as a service.",
    summary="Modular REST API bootstrap on top of LangChain. Create embeddings associated with a project tenant and interact using a LLM. RAG as a service.",
    version="2.1.0",
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

brain = Brain()


@app.get("/")
async def get(request: Request):
    return "RESTAI, so many 'A's and 'I's, so little time..."


@app.get("/info")
async def get_info(request: Request):
    return {
        "version": app.version, "embeddings": list(
            EMBEDDINGS.keys()), "llms": list(
            LLMS.keys()), "loaders": list(
                LOADERS.keys())}


@app.get("/hardware")
def get_hardware_info():
    try:
        cpu_load = psutil.cpu_percent()
        ram_usage = psutil.virtual_memory().percent

        gpu_load = None
        gpu_temp = None
        gpu_ram_usage = None
        gpu_power_consumption = None

        GPUs = GPUtil.getGPUs()
        if len(GPUs) > 0:
            gpu = GPUs[0]
            gpu_load = getattr(gpu, 'load', None)
            gpu_temp = getattr(gpu, 'temperature', None)
            gpu_ram_usage = getattr(gpu, 'memoryUtil', None)
            gpu_power_consumption = getattr(gpu, 'powerDraw', None)

        cpu_load = int(cpu_load)
        if gpu_load is not None:
            gpu_load = int(gpu_load * 100)
        
        if gpu_ram_usage is not None:
            gpu_ram_usage = int(gpu_ram_usage * 100)

        return {
            "cpu_load": cpu_load,
            "ram_usage": ram_usage,
            "gpu_load": gpu_load,
            "gpu_temp": gpu_temp,
            "gpu_ram_usage": gpu_ram_usage,
            "gpu_power_consumption": gpu_power_consumption,
        }
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail='{"error": ' + str(e) + '}')


@app.get("/projects")
async def get_projects(request: Request):
    return {"projects": brain.listProjects()}


@app.get("/projects/{projectName}")
async def get_project(projectName: str):
    try:
        project = brain.findProject(projectName)
        dbInfo = project.db.get()

        return {
            "project": project.model.name,
            "llm": project.model.llm,
            "embeddings": project.model.embeddings,
            "documents": len(
                dbInfo["documents"]),
            "metadatas": len(
                dbInfo["metadatas"]),
            "system": project.model.system}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail='{"error": ' + str(e) + '}')


@app.delete("/projects/{projectName}")
async def delete_project(projectName: str):
    try:
        if brain.deleteProject(projectName):
            return {"project": projectName}
        else:
            raise HTTPException(
                status_code=404, detail='{"error": "Project not found"}')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        if e.detail:
            raise e
        else:
            raise HTTPException(
                status_code=500, detail='{"error": ' + str(e) + '}')


@app.patch("/projects/{projectName}")
async def edit_project(projectModel: ProjectModel):
    try:
        if brain.editProject(projectModel):
            return {"project": projectModel.name}
        else:
            raise HTTPException(
                status_code=404, detail='{"error": "Project not found"}')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        if e.detail:
            raise e
        else:
            raise HTTPException(
                status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects")
async def create_project(projectModel: ProjectModel):
    try:
        brain.createProject(projectModel)
        return {"project": projectModel.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/embeddings/reset")
def project_reset(projectName: str):
    try:
        project = brain.findProject(projectName)
        project.db._client.reset()
        brain.initializeEmbeddings(project)

        return {"project": project.model.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/embeddings/find")
def get_embedding(projectName: str, embedding: EmbeddingModel):
    project = brain.findProject(projectName)
    docs = None

    collection = project.db._client.get_collection("langchain")
    if embedding.source.startswith(('http://', 'https://')):
        docs = collection.get(where={'source': embedding.source})
    else:
        docs = collection.get(where={'source': os.path.join(
            os.environ["UPLOADS_PATH"], project.model.name, embedding.source)})

    if (len(docs['ids']) == 0):
        return {"ids": []}
    else:
        return docs


@app.delete("/projects/{projectName}/embeddings/{id}")
def delete_embedding(projectName: str, id: str):
    project = brain.findProject(projectName)

    collection = project.db._client.get_collection("langchain")
    ids = collection.get(ids=[id])['ids']
    if len(ids):
        collection.delete(ids)
    return {"deleted": len(ids)}


@app.post("/projects/{projectName}/embeddings/ingest/url")
def ingest_url(projectName: str, ingest: IngestModel):
    try:
        project = brain.findProject(projectName)

        if ingest.recursive:
            loader = RecursiveUrlLoader(
                url=ingest.url,
                max_depth=ingest.depth,
                extractor=lambda x: Soup(
                    x,
                    "html.parser").text)
        else:
            loader = loader = SeleniumURLLoader(urls=[ingest.url])

        documents = loader.load()

        documents = ExtractKeywordsForMetadata(documents)

        ids = IndexDocuments(brain, project, documents)
        project.db.persist()

        return {"url": ingest.url, "documents": len(ids)}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/embeddings/ingest/upload")
def ingest_file(projectName: str, file: UploadFile):
    try:
        logger = logging.getLogger("embeddings_ingest_upload")
        project = brain.findProject(projectName)

        dest = os.path.join(os.environ["UPLOADS_PATH"],
                            project.model.name, file.filename)
        logger.info("Ingesting upload for destination: {}".format(dest))

        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        _, ext = os.path.splitext(file.filename or '')
        logger.debug("Filename: {}".format(file.filename))
        logger.debug("ContentType: {}".format(file.content_type))
        logger.debug("Extension: {}".format(ext))
        loader = FindFileLoader(dest, ext)
        documents = loader.load()

        documents = ExtractKeywordsForMetadata(documents)

        ids = IndexDocuments(brain, project, documents)
        logger.debug("Documents: {}".format(len(ids)))
        project.db.persist()
        logger.debug("Persisten project to DB")

        return {
            "filename": file.filename,
            "type": file.content_type,
            "documents": len(ids)}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.get('/projects/{projectName}/embeddings/urls')
def list_urls(projectName: str):
    project = brain.findProject(projectName)

    collection = project.db._client.get_collection("langchain")

    docs = collection.get(
        include=["metadatas"]
    )

    urls = []

    for metadata in docs["metadatas"]:
        if metadata["source"].startswith(
                ('http://', 'https://')) and metadata["source"] not in urls:
            urls.append(metadata["source"])

    return {'urls': urls}


@app.get('/projects/{projectName}/embeddings/files')
def list_files(projectName: str):
    project = brain.findProject(projectName)
    project_path = os.path.join(os.environ["UPLOADS_PATH"], project.model.name)

    if not os.path.exists(project_path):
        return {'error': f'Project {projectName} not found'}

    if not os.path.isdir(project_path):
        return {'error': f'{project_path} is not a directory'}

    files = [f for f in os.listdir(project_path) if os.path.isfile(
        os.path.join(project_path, f))]
    return {'files': files}


@app.delete('/projects/{projectName}/embeddings/url/{url}')
def delete_url(projectName: str, url: str):
    project = brain.findProject(projectName)

    collection = project.db._client.get_collection("langchain")
    ids = collection.get(
        where={'source': base64.b64decode(url).decode('utf-8')})['ids']
    if len(ids):
        collection.delete(ids)

    return {"deleted": len(ids)}


@app.delete('/projects/{projectName}/embeddings/files/{fileName}')
def delete_file(projectName: str, fileName: str):
    project = brain.findProject(projectName)

    collection = project.db._client.get_collection("langchain")
    ids = collection.get(
        where={
            'source': os.path.join(
                os.environ["UPLOADS_PATH"],
                project.model.name,
                base64.b64decode(fileName).decode('utf-8'))})['ids']
    if len(ids):
        collection.delete(ids)

    project_path = os.path.join(os.environ["UPLOADS_PATH"], project.model.name)

    file_path = os.path.join(
        project_path, base64.b64decode(fileName).decode('utf-8'))
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, detail="{'error': f'File {fileName} not found'}")
    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=404, detail="{'error': f'File {fileName} not found'}")

    os.remove(file_path)

    return {"deleted": len(ids)}


@app.post("/projects/{projectName}/question")
def question_project(projectName: str, input: QuestionModel):
    try:
        project = brain.findProject(projectName)
        if input.system or project.model.system:
            answer, hits = brain.questionContext(project, input)
            return {"question": input.question, "answer": answer, "hits": hits, "type": "questioncontext"}
        else:
            answer = brain.question(project, input)
            return {"question": input.question, "answer": answer, "type": "question"}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/chat")
def chat_project(projectName: str, input: ChatModel):
    try:
        project = brain.findProject(projectName)
        chat, response = brain.chat(project, input)

        return {"message": input.message, "response": response, "id": chat.id}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


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
