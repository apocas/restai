import logging
import os
import uvicorn
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, HTTPException, Request, UploadFile
from langchain.document_loaders import (
    WebBaseLoader,
)
from dotenv import load_dotenv
from brain import Brain

from project import IngestModel, ProjectModel
from tools import FindFileLoader, IndexDocuments

load_dotenv()

if os.environ["EMBEDDINGS_PATH"] is None:
    os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

app = FastAPI()
brain = Brain()

@app.get("/")
async def get(request: Request):
    return "REST AI API, so many 'A's and 'I's, so little time..."


@app.get("/projects")
async def getEmbeddings(request: Request):
    return {"projects": brain.listProjects()}

@app.get("/projects/{projectName}")
async def getProject(projectName: str):
    project = brain.loadProject(projectName)
    dbInfo = project.db.get()

    return {"project": project.model.name, "embeddings": project.model.embeddings, "documents": len(dbInfo["documents"]), "metadatas": len(dbInfo["metadatas"])}

@app.post("/projects")
async def createProject(projectModel: ProjectModel):
    try:
        brain.createProject(projectModel)
        return {"project": projectModel.name}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": ' + str(e) + '}')


@app.post("/projects/{projectName}/ingest/url")
def ingest(projectName: str, ingest: IngestModel):
    project = brain.loadProject(projectName)

    loader = WebBaseLoader(ingest.url)
    documents = loader.load()

    texts = IndexDocuments(brain, project, documents)
    project.db.persist()

    return {"url": ingest.url, "texts": len(texts), "documents": len(documents)}


@app.post("/projects/{projectName}/ingest/upload")
def uploadIngest(projectName: str, file: UploadFile):
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
