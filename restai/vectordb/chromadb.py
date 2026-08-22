import logging
import os
import shutil
from restai import config
import chromadb
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext

from restai.brain import Brain
from restai.embedding import Embedding
from restai.config import EMBEDDINGS_PATH
from restai.vectordb.tools import find_embeddings_path
from llama_index.vector_stores.chroma import ChromaVectorStore
from restai.vectordb.base import VectorBase
import restai.config as _cfg

logging.basicConfig(level=config.LOG_LEVEL)

# Cache PersistentClient per path so multiple workers don't pile up SQLite
# connections to the same directory. `patch_settings` clears the cache on
# vectordb_* changes so admins can swap Chroma host without restart.
_client_cache = {}


def _get_client(path=None):
    """Get or create a ChromaDB client, reusing PersistentClient per path.

    `_cfg.X` resolves through GUI settings each call — `from restai.config
    import CHROMADB_HOST` would freeze the value at import time.
    """
    host = _cfg.CHROMADB_HOST
    if host:
        return chromadb.HttpClient(host=host, port=_cfg.CHROMADB_PORT)
    if path not in _client_cache:
        _client_cache[path] = chromadb.PersistentClient(path=path)
    return _client_cache[path]


# ChromaDB is the only backend with a MINIMUM name length: collection names
# must be 3-512 chars. `project_store_key` returns `p{id}`, so every project
# with a single-digit id produced a 2-char name and `get_or_create_collection`
# raised InvalidArgumentError — i.e. on a fresh install the first nine projects
# could not be created at all (500 from POST /projects).
_CHROMA_MIN_NAME_LEN = 3


def _chroma_collection_name(store_key: str) -> str:
    """Collection name for `store_key`, satisfying ChromaDB's length floor.

    Zero-pads the numeric suffix (`p1` -> `p01`) instead of appending a
    sentinel, so the name keeps its `p<digits>` shape and cannot collide with
    another project (`p01` != `p10`, and ids are unique).

    Deliberately local to this backend rather than folded into
    `project_store_key`: `store_key` still names the on-disk embeddings
    directory and the pgvector / pinecone / weaviate identifiers, all of which
    accept a 2-char name today. Changing it globally would orphan those stores
    for every existing project with a single-digit id, whereas no ChromaDB
    collection can exist under the short name — creating one always failed.
    """
    if len(store_key) >= _CHROMA_MIN_NAME_LEN:
        return store_key
    return store_key[0] + store_key[1:].zfill(_CHROMA_MIN_NAME_LEN - 1)


class ChromaDBVector(VectorBase):
    db = None
    chroma_collection = None
    collection_name = None

    def __init__(self, brain, project, embedding: Embedding):
        super().__init__(brain, project, embedding)
        # The directory stays keyed on `store_key`; only the collection name is
        # padded, so an existing project's embeddings dir is never orphaned.
        path = find_embeddings_path(self.store_key)
        self.collection_name = _chroma_collection_name(self.store_key)
        self.db = _get_client(path)
        self.chroma_collection = self.db.get_or_create_collection(self.collection_name)
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
            self.db.delete_collection(name=self.collection_name)
            embeddingsPath = os.path.join(EMBEDDINGS_PATH, self.store_key)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
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
        self.db.delete_collection(name=self.collection_name)
        self.chroma_collection = self.db.get_or_create_collection(self.collection_name)
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
