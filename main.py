import logging
import os
from tempfile import NamedTemporaryFile
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.document_loaders import PyPDFLoader
from langchain.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
embeddingsPath = "./embeddings/"
embeddings = OpenAIEmbeddings()

text_splitter = CharacterTextSplitter(
    separator=" ", chunk_size=1000, chunk_overlap=0
)


@app.get("/")
async def get(request: Request):
    return "REST AI API, so many 'A' and 'I's, so little time..."


@app.get("/embeddings")
async def get(request: Request):
    return {"projects": [d for d in os.listdir(embeddingsPath) if os.path.isdir(os.path.join(embeddingsPath, d))]}


@app.post("/embeddings/{project}/create/")
async def createProject(project: str):
    os.mkdir(os.path.join(embeddingsPath, project))
    return {"project": project}


@app.post("/embeddings/{project}/upload")
def create_upload_file(project: str, file: UploadFile):
    db = Chroma(
        persist_directory=os.path.join(embeddingsPath, project), embedding_function=embeddings
    )

    temp = NamedTemporaryFile(delete=False)
    try:
        try:
            contents = file.file.read()
            with temp as f:
                f.write(contents)
        except Exception:
            raise HTTPException(
                status_code=500, detail='Error on uploading the file')
        finally:
            file.file.close()

        match file.content_type:
            case "text/plain":
                loader = TextLoader(temp.name)
            case "application/pdf":
                loader = PyPDFLoader(temp.name)
            case _:
                raise HTTPException(
                    status_code=500, detail='{"error": "Invalid file type."}')
        texts = text_splitter.split_documents(loader.load())
    except Exception:
        raise HTTPException(
            status_code=500, detail='{"error": "Something went wrong."}')
    finally:
        os.remove(temp.name)

    texts_final = [doc.page_content for doc in texts]
    metadatas = [doc.metadata for doc in texts]

    db.add_texts(texts=texts_final, metadatas=metadatas)

    return {"filename": file.filename, "type": file.content_type}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
