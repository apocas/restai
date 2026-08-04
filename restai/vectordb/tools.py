import os
from typing import Iterable

import yake
from llama_index.core.schema import Document
from llama_index.core.text_splitter import TokenTextSplitter, SentenceSplitter

from restai.config import EMBEDDINGS_PATH

from modules.loaders import LOADERS

from llama_index.core.node_parser.interface import MetadataAwareTextSplitter
from llama_index.core.node_parser import MarkdownNodeParser

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from restai.project import Project
    from restai.vectordb.base import VectorBase


def get_available_vectorstores() -> list[str]:
    """Backends to surface in the project-create vectorstore dropdown.

    `_cfg.X` reads through `restai.config.__getattr__` to the DB each call
    so GUI toggles in Settings → VectorDBs take effect on next page load.
    """
    import restai.config as _cfg
    available = []
    if _cfg.CHROMADB_ENABLED:
        available.append("chroma")
    if _cfg.PGVECTOR_ENABLED:
        available.append("pgvector")
    if _cfg.WEAVIATE_ENABLED:
        available.append("weaviate")
    if _cfg.PINECONE_ENABLED:
        available.append("pinecone")
    return available


def find_vector_db(project: "Project") -> type["VectorBase"]:
    # A RAG project created without an explicit vectorstore (e.g. via the API,
    # where the field is optional) defaults to ChromaDB — the platform default,
    # same as the frontend's create wizard.
    if not project.props.vectorstore or project.props.vectorstore in ("chromadb", "chroma"):
        from restai.vectordb.chromadb import ChromaDBVector
        return ChromaDBVector
    elif project.props.vectorstore == "pgvector":
        from restai.vectordb.pgvector import PGVectorDB
        return PGVectorDB
    elif project.props.vectorstore == "weaviate":
        from restai.vectordb.weaviate import WeaviateDB
        return WeaviateDB
    elif project.props.vectorstore == "pinecone":
        from restai.vectordb.pinecone import PineconeDB
        return PineconeDB
    else:
        raise Exception("Invalid vectorDB type.")


def index_documents_classic(project: "Project", documents: Iterable[Document], splitter: str = "sentence",
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
  
def index_documents_docling(project: "Project", documents: Iterable[Document]) -> int:
    parser = MarkdownNodeParser()
    
    nodes = parser.get_nodes_from_documents(documents)

    project.vector.index.insert_nodes(nodes)
    
    return len(nodes)


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


def project_store_key(project) -> str:
    """Stable storage identity for a project's vector store.

    Keyed on the immutable id, not the mutable name. Name-derived keys had to be
    sanitized per backend, which was lossy — `hr-salaries` and `hr_salaries`
    collapsed onto one store while `projects.name` is unique on the raw string —
    and they moved on rename. `p{id}` needs no sanitizing and cannot collide.
    """
    pid = getattr(getattr(project, "props", None), "id", None)
    if pid is None:
        raise ValueError("Project has no id; cannot derive a vector store key")
    return f"p{int(pid)}"


def find_embeddings_path(store_key: str) -> str:
    """Directory holding this project's Chroma store, creating it if needed."""
    os.makedirs(EMBEDDINGS_PATH, exist_ok=True)
    target = os.path.join(EMBEDDINGS_PATH, store_key)
    os.makedirs(target, exist_ok=True)
    return target
