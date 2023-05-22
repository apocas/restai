import logging
import os
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, HTTPException, Request, UploadFile
from langchain.document_loaders import (
    WebBaseLoader,
)
from langchain.chains import RetrievalQA
from dotenv import load_dotenv
from app.brain import Brain

from app.models import IngestModel, ProjectModel, QuestionModel, ChatModel
from app.tools import FindFileLoader, IndexDocuments

load_dotenv()

if "EMBEDDINGS_PATH" not in os.environ:
    os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

if "PROJECTS_PATH" not in os.environ:
    os.environ["PROJECTS_PATH"] = "./projects/"

app = FastAPI()
brain = Brain()


@app.get("/")
async def get(request: Request):
    return "REST AI API, so many 'A's and 'I's, so little time..."


@app.get("/projects")
async def getProjects(request: Request):
    return {"projects": brain.listProjects()}


@app.get("/projects/{projectName}")
async def getProject(projectName: str):
    try:
        project = brain.loadProject(projectName)
        dbInfo = project.db.get()

        return {"project": project.model.name, "embeddings": project.model.embeddings, "documents": len(dbInfo["documents"]), "metadatas": len(dbInfo["metadatas"])}
    except Exception as e:
        raise HTTPException(
            status_code=404, detail='{"error": ' + str(e) + '}')


@app.delete("/projects/{projectName}")
async def deleteProject(projectName: str):
    try:
        brain.deleteProject(projectName)
        return {"project": projectName}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects")
async def createProject(projectModel: ProjectModel):
    try:
        brain.createProject(projectModel)
        return {"project": projectModel.name}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/ingest/url")
def ingestURL(projectName: str, ingest: IngestModel):
    try:
        project = brain.loadProject(projectName)

        loader = WebBaseLoader(ingest.url)
        documents = loader.load()

        texts = IndexDocuments(brain, project, documents)
        project.db.persist()

        return {"url": ingest.url, "texts": len(texts), "documents": len(documents)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/ingest/upload")
def ingestFile(projectName: str, file: UploadFile):
    try:
        project = brain.loadProject(projectName)

        temp = NamedTemporaryFile(delete=False)
        try:
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
            loader = FindFileLoader(temp, ext)
            documents = loader.load()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail='{"error": "Something went wrong."}')
        finally:
            os.remove(temp.name)

        texts = IndexDocuments(brain, project, documents)
        project.db.persist()

        return {"filename": file.filename, "type": file.content_type, "texts": len(texts), "documents": len(documents)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/question")
def questionProject(projectName: str, input: QuestionModel):
    try:
        project = brain.loadProject(projectName)
        answer = brain.question(project, input)
        return {"question": input.question, "answer": answer.strip()}
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/chat")
def chatProject(projectName: str, input: ChatModel):
    try:
        project = brain.loadProject(projectName)
        return "Not implemented yet."
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')
