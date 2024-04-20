import shutil
import redis
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext

from app.vectordb.tools import FindEmbeddingsPath
from llama_index.vector_stores.redis import RedisVectorStore

from app.config import REDIS_HOST, REDIS_PORT
from app.vectordb.base import VectorBase

class RedisVector(VectorBase):
    redis = None
  
    def __init__(self, brain, project):
        self.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True)
        self.project = project
        self.index = self._vector_init(brain)
    
    def _vector_init(self, brain):
        vector_store = RedisVectorStore(
            redis_url=f"redis://{REDIS_HOST}:{REDIS_PORT}",
            index_name=self.project.model.name,
            metadata_fields=["source", "keywords"],
            index_prefix="llama_" + self.project.model.name,
            overwrite=False)

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store)
        return VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context, embed_model=brain.getEmbedding(self.project.model.embeddings))


    def save(self):
        try:
            self.redis.vector_store.persist(persist_path="")
        except BaseException:
            print("REDIS - Error saving vectors")

    def load(self, brain):
        pass

    def list(self):
        output = []
      
        keys = self.redis.keys("llama_" + self.project.model.name + "/*")
        for key in keys:
            source = self.redis.hget(key, "source")
            if source not in output:
                output.append(source)

        return output


    def list_source(self, source):
        output = []
      
        keys = self.redis.keys("llama_" + self.project.model.name + "/*")
        for key in keys:
            sourcer = self.redis.hget(key, "source").strip()
            id = self.redis.hget(key, "id").strip()
            if source == sourcer:
                output.append({"source": source, "id": id})

        return output


    def info(self):
        keys = self.redis.keys("llama_" + self.project.model.name + "/*")
        return len(keys)


    def find_source(self, source):
        keys = self.redis.keys("llama_" + self.project.model.name + "/*")
        ids = []
        metadatas = []
        documents = []
        for key in keys:
            lsource = self.redis.hget(key, "source")
            if lsource == source:
                ids.append(key)
                metadatas.append(
                    {"source": lsource, "keywords": self.redis.hget(key, "keywords")})
                documents.append(self.redis.hget(key, "text"))

        return {"ids": ids, "metadatas": metadatas, "documents": documents}


    def find_id(self, id):
        output = {"id": id}
        
        ids = "llama_" + self.project.model.name + "/vector_" + id
        keys = self.redis.hkeys(ids)
        keys = [k for k in keys if not k.startswith(
            '_') and k != "vector" and k != "text" and k != "doc_id" and k != "id"]
        data = self.redis.hmget(ids, keys)
        text = self.redis.hget(ids, "text")
        output["metadata"] = dict(zip(keys, data))
        output["document"] = text

        return output


    def delete(self):
        try:
            self.redis.ft(self.project.model.name).dropindex(True)
            embeddingsPath = FindEmbeddingsPath(self.project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass
        

    def delete_source(self, source):
        ids = []
        keys = self.redis.keys("llama_" + self.project.model.name + "/*")
        for key in keys:
            lsource = self.redis.hget(key, "source")
            if lsource == source:
                ids.append(key)
                self.redis.delete(key)
        return ids


    def delete_id(self, id):
        self.redis.delete(id)
        return id


    def reset(self, brain):
        self.delete()
        self.index = self._vector_init(brain)