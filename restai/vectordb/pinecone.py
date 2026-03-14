import logging
import re

from pinecone import Pinecone
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext
from llama_index.vector_stores.pinecone import PineconeVectorStore

from restai import config
from restai.brain import Brain
from restai.embedding import Embedding
from restai.vectordb.base import VectorBase
from restai.config import PINECONE_API_KEY, PINECONE_INDEX

logging.basicConfig(level=config.LOG_LEVEL)


def _sanitize_namespace(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).lower()


class PineconeDB(VectorBase):
    def __init__(self, brain: Brain, project, embedding: Embedding):
        self.project = project
        self.embedding = embedding
        self.namespace = _sanitize_namespace(project.props.name)

        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        self.pinecone_index = self.pc.Index(PINECONE_INDEX)
        self.index = self._vector_init(brain)

    def _vector_init(self, brain: Brain):
        vector_store = PineconeVectorStore(
            pinecone_index=self.pinecone_index,
            namespace=self.namespace,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        return VectorStoreIndex.from_vector_store(
            vector_store,
            storage_context=storage_context,
            embed_model=self.embedding.embedding,
        )

    def save(self):
        pass

    def load(self, brain: Brain):
        pass

    def list(self):
        output = []
        try:
            for ids_batch in self.pinecone_index.list(namespace=self.namespace):
                fetched = self.pinecone_index.fetch(
                    ids=ids_batch, namespace=self.namespace
                )
                for vec in fetched.vectors.values():
                    source = (vec.metadata or {}).get("source")
                    if source and source not in output:
                        output.append(source)
        except Exception:
            pass
        return output

    def list_source(self, source: str):
        output = []
        try:
            for ids_batch in self.pinecone_index.list(namespace=self.namespace):
                fetched = self.pinecone_index.fetch(
                    ids=ids_batch, namespace=self.namespace
                )
                for vec in fetched.vectors.values():
                    if (vec.metadata or {}).get("source") == source:
                        output.append(source)
        except Exception:
            pass
        return output

    def info(self):
        try:
            stats = self.pinecone_index.describe_index_stats()
            ns_stats = stats.namespaces.get(self.namespace)
            return ns_stats.vector_count if ns_stats else 0
        except Exception:
            return 0

    def find_source(self, source: str):
        ids = []
        metadatas = []
        documents = []
        try:
            for ids_batch in self.pinecone_index.list(namespace=self.namespace):
                fetched = self.pinecone_index.fetch(
                    ids=ids_batch, namespace=self.namespace
                )
                for vid, vec in fetched.vectors.items():
                    meta = vec.metadata or {}
                    if meta.get("source") == source:
                        ids.append(vid)
                        metadatas.append(
                            {k: v for k, v in meta.items() if k != "text"}
                        )
                        documents.append(meta.get("text", ""))
        except Exception:
            pass
        return {"ids": ids, "metadatas": metadatas, "documents": documents}

    def find_id(self, id: str):
        output = {"id": id}
        try:
            fetched = self.pinecone_index.fetch(
                ids=[id], namespace=self.namespace
            )
            vec = fetched.vectors.get(id)
            if vec:
                meta = vec.metadata or {}
                output["metadata"] = {
                    k: v for k, v in meta.items()
                    if not k.startswith("_") and k != "text"
                }
                output["document"] = meta.get("text", "")
        except Exception:
            pass
        return output

    def delete(self):
        try:
            self.pinecone_index.delete(
                delete_all=True, namespace=self.namespace
            )
        except Exception as e:
            logging.exception(e)

    def delete_source(self, source: str):
        ids = []
        try:
            for ids_batch in self.pinecone_index.list(namespace=self.namespace):
                fetched = self.pinecone_index.fetch(
                    ids=ids_batch, namespace=self.namespace
                )
                for vid, vec in fetched.vectors.items():
                    if (vec.metadata or {}).get("source") == source:
                        ids.append(vid)
            if ids:
                for i in range(0, len(ids), 1000):
                    self.pinecone_index.delete(
                        ids=ids[i:i + 1000], namespace=self.namespace
                    )
        except Exception as e:
            logging.exception(e)
        return ids

    def delete_id(self, id: str):
        try:
            self.pinecone_index.delete(
                ids=[id], namespace=self.namespace
            )
        except Exception as e:
            logging.exception(e)
        return id

    def reset(self, brain: Brain):
        self.delete()
        self.index = self._vector_init(brain)
