import logging
import os
import shutil
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, HTTPException, Request, UploadFile
from langchain.document_loaders import (
    WebBaseLoader,
)
from dotenv import load_dotenv
from app.brain import Brain

from app.models import EmbeddingModel, IngestModel, ProjectModel, QuestionModel, ChatModel
from app.tools import FindFileLoader, IndexDocuments
from fastapi.openapi.utils import get_openapi

from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS
from modules.loaders import LOADERS

load_dotenv()

if "EMBEDDINGS_PATH" not in os.environ:
    os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

if "UPLOADS_PATH" not in os.environ:
    os.environ["UPLOADS_PATH"] = "./uploads/"

if "PROJECTS_PATH" not in os.environ:
    os.environ["PROJECTS_PATH"] = "./projects/"
    
os.environ["ALLOW_RESET"] = "true"

app = FastAPI(
    title="RestAI",
    description="Modular REST API bootstrap on top of LangChain. Create embeddings associated with a project tenant and interact using a LLM. RAG as a service.",
    summary="Modular REST API bootstrap on top of LangChain. Create embeddings associated with a project tenant and interact using a LLM. RAG as a service.",
    version="2.0.0",
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

brain = Brain()

@app.get("/")
async def get(request: Request):
    return "RESTAI, so many 'A's and 'I's, so little time..."
  
@app.get("/info")
async def getInfo(request: Request):
    return {"version": app.version, "embeddings": list(EMBEDDINGS.keys()), "llms": list(LLMS.keys()), "loaders": list(LOADERS.keys())}


@app.get("/projects")
async def getProjects(request: Request):
    return {"projects": brain.listProjects()}


@app.get("/projects/{projectName}")
async def getProject(projectName: str):
    try:
        project = brain.findProject(projectName)
        dbInfo = project.db.get()

        return {"project": project.model.name, "llm": project.model.llm , "embeddings": project.model.embeddings, "documents": len(dbInfo["documents"]), "metadatas": len(dbInfo["metadatas"])}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=404, detail='{"error": ' + str(e) + '}')

@app.delete("/projects/{projectName}")
async def deleteProject(projectName: str):
    try:
        brain.deleteProject(projectName)
        return {"project": projectName}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects")
async def createProject(projectModel: ProjectModel):
    try:
        brain.createProject(projectModel)
        return {"project": projectModel.name}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')
        
@app.post("/projects/{projectName}/embeddings/reset")
def reset(projectName: str):
    try:
        project = brain.findProject(projectName)
        project.db._client.reset()
        brain.initializeEmbeddings(project)

        return {"project": project.model.name}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=404, detail='{"error": ' + str(e) + '}')
        
@app.post("/projects/{projectName}/embeddings/find")
def getEmbedding(projectName: str, embedding: EmbeddingModel):
    project = brain.findProject(projectName)

    collection = project.db._client.get_collection("langchain")
    ids = collection.get(where = {'source': os.path.join(os.path.join(os.environ["UPLOADS_PATH"], project.model.name), embedding.source)})['ids']
    
    if(len(ids) == 0):
        return {"ids": []}
    else:
      return collection.get(ids = ids)

@app.post("/projects/{projectName}/embeddings/delete")
def deleteEmbedding(projectName: str, embedding: EmbeddingModel):
    project = brain.findProject(projectName)

    collection = project.db._client.get_collection("langchain")
    ids = collection.get(where = {'source': os.path.join(os.path.join(os.environ["UPLOADS_PATH"], project.model.name), embedding.source)})['ids']
    if len(ids): collection.delete(ids)
    return {"deleted": len(ids)}

@app.post("/projects/{projectName}/embeddings/ingest/url")
def ingestURL(projectName: str, ingest: IngestModel):
    try:
        project = brain.findProject(projectName)

        loader = WebBaseLoader(ingest.url)
        documents = loader.load()

        texts = IndexDocuments(brain, project, documents)
        project.db.persist()

        return {"url": ingest.url, "texts": len(texts), "documents": len(documents)}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')

@app.post("/projects/{projectName}/embeddings/ingest/upload")
def ingestFile(projectName: str, file: UploadFile):
    try:
        project = brain.findProject(projectName)
        
        dest = os.path.join(os.path.join(os.environ["UPLOADS_PATH"], project.model.name), file.filename)

        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
      
        _, ext = os.path.splitext(file.filename or '')
        loader = FindFileLoader(dest, ext)
        documents = loader.load()

        texts = IndexDocuments(brain, project, documents)
        project.db.persist()

        return {"filename": file.filename, "type": file.content_type, "texts": len(texts), "documents": len(documents)}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')

@app.get('/projects/{projectName}/embeddings/files')
def list_files(projectName: str):
    project = brain.findProject(projectName)
    project_path = os.path.join(os.environ["UPLOADS_PATH"], project.model.name)
    
    if not os.path.exists(project_path):
        return {'error': f'Project {projectName} not found'}
      
    if not os.path.isdir(project_path):
        return {'error': f'{project_path} is not a directory'}
      
    files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
    return {'files': files}

@app.delete('/projects/{projectName}/embeddings/files/{fileName}')
def delete_file(projectName: str, fileName: str):
    project = brain.findProject(projectName)
    
    collection = project.db._client.get_collection("langchain")
    ids = collection.get(where = {'source': os.path.join(os.path.join(os.environ["UPLOADS_PATH"], project.model.name), fileName)})['ids']
    if len(ids): collection.delete(ids)
    
    project_path = os.path.join(os.environ["UPLOADS_PATH"], project.model.name)
    
    file_path = os.path.join(project_path, fileName)
    if not os.path.exists(file_path):
        return {'error': f'File {fileName} not found'}
    if not os.path.isfile(file_path):
        return {'error': f'{file_path} is not a file'}
    os.remove(file_path)
    
    return {"deleted": len(ids)}

@app.post("/projects/{projectName}/question")
def questionProject(projectName: str, input: QuestionModel):
    try:
        project = brain.findProject(projectName)
        if input.system:
            answer = brain.questionContext(project, input)
        else:
            answer = brain.question(project, input)
        return {"question": input.question, "answer": answer}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/chat")
def chatProject(projectName: str, input: ChatModel):
    try:
        project = brain.findProject(projectName)
        chat, response = brain.chat(project, input)

        return {"message": input.message, "response": response, "id": chat.id}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')
