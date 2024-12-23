import os
import re
import time
from typing import Iterable

import yake
from llama_index.core.schema import Document
from llama_index.core.text_splitter import TokenTextSplitter, SentenceSplitter

from app.config import EMBEDDINGS_PATH
from app.config import REDIS_HOST, PINECONE_API_KEY
from app.project import Project
from app.vectordb.base import VectorBase
from modules.loaders import LOADERS

from llama_index.core.node_parser.interface import MetadataAwareTextSplitter


def find_vector_db(project: Project) -> type[VectorBase]:
    if project.model.vectorstore == "redis" and REDIS_HOST:
        from app.vectordb.redis import RedisVector
        return RedisVector
    elif project.model.vectorstore == "chromadb" or project.model.vectorstore == "chroma":
        from app.vectordb.chromadb import ChromaDBVector
        return ChromaDBVector
    elif project.model.vectorstore == "pinecone" and PINECONE_API_KEY:
        from app.vectordb.pinecone import PineconeVector
        return PineconeVector
    else:
        raise Exception("Invalid vectorDB type.")


def index_documents(project: Project, documents: Iterable[Document], splitter: str = "sentence",
                    chunks: int = 256) -> int: # TODO: Replace splitter string ID with enum
    splitter_o: MetadataAwareTextSplitter
    match splitter:
        case "sentence":
            splitter_o = TokenTextSplitter(
            separator=" ", chunk_size=chunks, chunk_overlap=30)
        case "token":
            splitter_o = SentenceSplitter(
                separator=" ", paragraph_separator="\n", chunk_size=chunks, chunk_overlap=30)
        case _:
            raise ValueError(f"Unknown splitter '{splitter}'.")

    total_chunks: int = 0

    document: Document
    for document in documents:
        text_chunks = splitter_o.split_text(document.text)

        doc_chunks: list[Document] = [Document(text=t, metadata=document.metadata)
                                      for t in text_chunks]

        for doc_chunk in doc_chunks:
            project.vector.index.insert(doc_chunk)
            total_chunks += 1

    return total_chunks


def extract_keywords_for_metadata(documents):
    max_ngram_size = 4
    numOfKeywords = 15
    kw_extractor = yake.KeywordExtractor(n=max_ngram_size, top=numOfKeywords)
    for document in documents:
        metadataKeywords = ""
        keywords = kw_extractor.extract_keywords(document.text)
        for kw in keywords:
            metadataKeywords = metadataKeywords + kw[0] + ", "
        document.metadata["keywords"] = metadataKeywords

    return documents


def find_file_loader(ext, eargs=None):
    if eargs is None:
        eargs = {}
    if ext in LOADERS:
        loader_class, loader_args = LOADERS[ext]
        loader = loader_class()
        return loader
    else:
        raise Exception("Invalid file type.")


def find_embeddings_path(projectName):
    embeddings_path = EMBEDDINGS_PATH
    embeddingsPathProject = None

    if not os.path.exists(embeddings_path):
        os.makedirs(embeddings_path)

    project_dirs = [d for d in os.listdir(
        embeddings_path) if os.path.isdir(os.path.join(embeddings_path, d))]

    for dir in project_dirs:
        if re.match(f'^{projectName}_[0-9]+$', dir):
            embeddingsPathProject = os.path.join(embeddings_path, dir)

    if embeddingsPathProject is None:
        embeddingsPathProject = os.path.join(
            embeddings_path, projectName + "_" + str(int(time.time())))
        os.mkdir(embeddingsPathProject)

    return embeddingsPathProject
