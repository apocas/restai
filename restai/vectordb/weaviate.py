import logging
import re

import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.query import Filter
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext
from llama_index.vector_stores.weaviate import WeaviateVectorStore

from restai import config
from restai.brain import Brain
from restai.embedding import Embedding
from restai.vectordb.base import VectorBase
from restai.config import (
    WEAVIATE_HOST,
    WEAVIATE_PORT,
    WEAVIATE_GRPC_PORT,
    WEAVIATE_API_KEY,
)

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)


def _sanitize_collection_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if sanitized and sanitized[0].isdigit():
        sanitized = "X" + sanitized
    if sanitized:
        sanitized = sanitized[0].upper() + sanitized[1:]
    return sanitized


class WeaviateDB(VectorBase):
    def __init__(self, brain: Brain, project, embedding: Embedding):
        self.project = project
        self.embedding = embedding
        self.collection_name = _sanitize_collection_name(project.props.name)

        if WEAVIATE_API_KEY:
            self.client = weaviate.connect_to_custom(
                http_host=WEAVIATE_HOST,
                http_port=int(WEAVIATE_PORT),
                http_secure=False,
                grpc_host=WEAVIATE_HOST,
                grpc_port=int(WEAVIATE_GRPC_PORT),
                grpc_secure=False,
                auth_credentials=AuthApiKey(WEAVIATE_API_KEY),
            )
        else:
            self.client = weaviate.connect_to_local(
                host=WEAVIATE_HOST,
                port=int(WEAVIATE_PORT),
                grpc_port=int(WEAVIATE_GRPC_PORT),
            )

        self.index = self._vector_init(brain)

    def _vector_init(self, brain: Brain):
        vector_store = WeaviateVectorStore(
            weaviate_client=self.client,
            index_name=self.collection_name,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        return VectorStoreIndex.from_vector_store(
            vector_store,
            storage_context=storage_context,
            embed_model=self.embedding.embedding,
        )

    def _get_collection(self):
        return self.client.collections.get(self.collection_name)

    def save(self):
        pass

    def load(self, brain: Brain):
        pass

    def list(self):
        output = []
        try:
            collection = self._get_collection()
            for obj in collection.iterator(return_properties=["source"]):
                source = obj.properties.get("source")
                if source and source not in output:
                    output.append(source)
        except Exception:
            pass
        return output

    def list_source(self, source: str):
        output = []
        try:
            collection = self._get_collection()
            response = collection.query.fetch_objects(
                filters=Filter.by_property("source").equal(source),
                return_properties=["source"],
            )
            for obj in response.objects:
                output.append(obj.properties.get("source"))
        except Exception:
            pass
        return output

    def info(self):
        try:
            collection = self._get_collection()
            result = collection.aggregate.over_all(total_count=True)
            return result.total_count
        except Exception:
            return 0

    def find_source(self, source: str):
        ids = []
        metadatas = []
        documents = []
        try:
            collection = self._get_collection()
            response = collection.query.fetch_objects(
                filters=Filter.by_property("source").equal(source),
            )
            for obj in response.objects:
                ids.append(str(obj.uuid))
                props = obj.properties or {}
                metadatas.append(
                    {k: v for k, v in props.items() if k != "text"}
                )
                documents.append(props.get("text", ""))
        except Exception:
            pass
        return {"ids": ids, "metadatas": metadatas, "documents": documents}

    def find_id(self, id: str):
        output = {"id": id}
        try:
            collection = self._get_collection()
            obj = collection.query.fetch_object_by_id(uuid=id)
            if obj:
                props = obj.properties or {}
                output["metadata"] = {
                    k: v for k, v in props.items()
                    if not k.startswith("_") and k != "text"
                }
                output["document"] = props.get("text", "")
        except Exception:
            pass
        return output

    def delete(self):
        try:
            self.client.collections.delete(self.collection_name)
        except Exception as e:
            logging.exception(e)

    def delete_source(self, source: str):
        ids = []
        try:
            collection = self._get_collection()
            response = collection.query.fetch_objects(
                filters=Filter.by_property("source").equal(source),
            )
            ids = [str(obj.uuid) for obj in response.objects]
            if ids:
                collection.data.delete_many(
                    where=Filter.by_property("source").equal(source)
                )
        except Exception as e:
            logging.exception(e)
        return ids

    def delete_id(self, id: str):
        try:
            collection = self._get_collection()
            collection.data.delete_by_id(uuid=id)
        except Exception as e:
            logging.exception(e)
        return id

    def reset(self, brain: Brain):
        self.delete()
        self.index = self._vector_init(brain)
