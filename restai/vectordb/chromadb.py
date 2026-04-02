import logging
from restai import config
import shutil
import chromadb
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext

from restai.brain import Brain
from restai.embedding import Embedding
from restai.vectordb.tools import find_embeddings_path
from llama_index.vector_stores.chroma import ChromaVectorStore
from restai.vectordb.base import VectorBase
from restai.config import CHROMADB_HOST, CHROMADB_PORT

logging.basicConfig(level=config.LOG_LEVEL)

# Cache PersistentClient instances per path to avoid creating multiple
# SQLite connections to the same directory within the same worker process.
_client_cache = {}


def _get_client(path=None):
    """Get or create a ChromaDB client, reusing PersistentClient per path."""
    if CHROMADB_HOST:
        return chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
    if path not in _client_cache:
        _client_cache[path] = chromadb.PersistentClient(path=path)
    return _client_cache[path]


class ChromaDBVector(VectorBase):
    db = None
    chroma_collection = None

    def __init__(self, brain, project, embedding: Embedding):
        path = find_embeddings_path(project.props.name)
        self.db = _get_client(path)
        self.chroma_collection = self.db.get_or_create_collection(project.props.name)
        self.project = project
        self.embedding = embedding
        self.index = self._vector_init(brain)

    def _vector_init(self, brain):
        vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        return VectorStoreIndex.from_vector_store(
            vector_store, storage_context=storage_context,
            embed_model=self.embedding.embedding)

    def save(self):
        pass

    def load(self, brain: Brain):
        pass

    def list(self):
        output = []
        docs = self.chroma_collection.get(include=["metadatas"])
        for metadata in docs["metadatas"]:
            if metadata["source"] not in output:
                output.append(metadata["source"])
        return output

    def list_source(self, source):
        output = []
        docs = self.chroma_collection.get(include=["metadatas"])
        for metadata in docs["metadatas"]:
            if metadata["source"] == source:
                output.append(metadata["source"])
        return output

    def info(self):
        docs = self.chroma_collection.get(include=["metadatas"])
        return len(docs["ids"])

    def find_source(self, source: str):
        return self.chroma_collection.get(where={'source': source})

    def find_id(self, id):
        output = {"id": id}
        docs = self.chroma_collection.get(ids=[id])
        output["metadata"] = {
            k: v for k, v in docs["metadatas"][0].items() if not k.startswith('_')}
        output["document"] = docs["documents"][0]
        return output

    def delete(self):
        try:
            self.db.delete_collection(name=self.project.props.name)
            embeddingsPath = find_embeddings_path(self.project.props.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
            # Remove cached client since the data is gone
            _client_cache.pop(embeddingsPath, None)
        except Exception as e:
            logging.exception(e)

    def delete_source(self, source):
        ids = self.chroma_collection.get(where={'source': source})['ids']
        if len(ids):
            self.chroma_collection.delete(ids)
        return ids

    def delete_id(self, id):
        ids = self.chroma_collection.get(ids=[id])['ids']
        if len(ids):
            self.chroma_collection.delete(ids)
        return id

    def reset(self, brain):
        self.db.delete_collection(name=self.project.props.name)
        self.chroma_collection = self.db.get_or_create_collection(self.project.props.name)
        self.index = self._vector_init(brain)

    def list_all_chunks(self, limit=50000):
        output = []
        docs = self.chroma_collection.get(include=["metadatas", "documents"])
        for i, doc_id in enumerate(docs["ids"][:limit]):
            output.append({
                "id": doc_id,
                "source": docs["metadatas"][i].get("source", "") if docs["metadatas"] else "",
                "text": docs["documents"][i] if docs["documents"] else "",
            })
        return output
