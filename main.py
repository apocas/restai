import logging
import os
from tempfile import NamedTemporaryFile
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.document_loaders import (
    CSVLoader,
    EverNoteLoader,
    PDFMinerLoader,
    TextLoader,
    UnstructuredEmailLoader,
    UnstructuredEPubLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
    UnstructuredODTLoader,
    UnstructuredPowerPointLoader,
    UnstructuredWordDocumentLoader,
)
from langchain.text_splitter import CharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

LOADERS_MAP = {
    ".csv": (CSVLoader, {}),
    ".doc": (UnstructuredWordDocumentLoader, {}),
    ".docx": (UnstructuredWordDocumentLoader, {}),
    ".enex": (EverNoteLoader, {}),
    ".eml": (UnstructuredEmailLoader, {}),
    ".epub": (UnstructuredEPubLoader, {}),
    ".html": (UnstructuredHTMLLoader, {}),
    ".md": (UnstructuredMarkdownLoader, {}),
    ".odt": (UnstructuredODTLoader, {}),
    ".pdf": (PDFMinerLoader, {}),
    ".ppt": (UnstructuredPowerPointLoader, {}),
    ".pptx": (UnstructuredPowerPointLoader, {}),
    ".txt": (TextLoader, {"encoding": "utf8"}),
}

app = FastAPI()
embeddingsPath = "./embeddings/"
embeddings = OpenAIEmbeddings()
#embeddings = HuggingFaceEmbeddings(model_name=HF_EMBEDDINGS_MODEL)

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
                status_code=500, detail='{"error": "Error while saving file."}')
        finally:
            file.file.close()

        _, ext = os.path.splitext(file.filename)
        if ext in LOADERS_MAP:
            loader_class, loader_args = LOADERS_MAP[ext]
            loader = loader_class(temp.name, **loader_args)
        else:
            raise HTTPException(
                status_code=500, detail='{"error": "Invalid file type."}')
        documents = loader.load()
        texts = text_splitter.split_documents(documents)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='{"error": "Something went wrong."}')
    finally:
        os.remove(temp.name)

    texts_final = [doc.page_content for doc in texts]
    metadatas = [doc.metadata for doc in texts]

    db.add_texts(texts=texts_final, metadatas=metadatas)

    return {"filename": file.filename, "type": file.content_type, "texts": len(texts_final), "documents": len(documents)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
