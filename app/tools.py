from langchain.embeddings import OpenAIEmbeddings
from langchain.embeddings import HuggingFaceEmbeddings
from fastapi import HTTPException

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

def GetEmbedding(name: str, model=None):
    embeddings = {
        "openai": OpenAIEmbeddings(),  # type: ignore
        "huggingface": HuggingFaceEmbeddings(model_name=model if model != None else "all-mpnet-base-v2"),
    }

    return embeddings[name]

def IndexDocuments(brain, project, documents):
    texts = brain.text_splitter.split_documents(documents)
    texts_final = [doc.page_content for doc in texts]
    metadatas = [doc.metadata for doc in texts]

    for metadata in metadatas:
      for key, value in list(metadata.items()):
        if value is None:
            del metadata[key]
    
    project.db.add_texts(texts=texts_final, metadatas=metadatas)
    return texts_final


def FindFileLoader(temp, ext):
    loaders = {
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

    if ext in loaders:
      loader_class, loader_args = loaders[ext]
      return loader_class(temp.name, **loader_args)
    else:
        raise HTTPException(status_code=500, detail='{"error": "Invalid file type."}')