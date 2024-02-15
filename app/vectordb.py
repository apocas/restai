import os
import shutil
import chromadb
import redis
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext

from app.tools import FindEmbeddingsPath
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.vector_stores.chroma import ChromaVectorStore

def vector_init(brain, project):
    path = FindEmbeddingsPath(project.model.name)

    if project.model.vectorstore == "chroma":
        db = chromadb.PersistentClient(path=path)
        chroma_collection = db.get_or_create_collection(project.model.name)
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(
            vector_store, storage_context=storage_context, embed_model=brain.getEmbedding(
            project.model.embeddings))
        return index
    elif project.model.vectorstore == "redis":
        if path is None or len(os.listdir(path)) == 0:
            vector_store = RedisVectorStore(
                redis_url="redis://" +
                os.environ["REDIS_HOST"] +
                ":" +
                os.environ["REDIS_PORT"],
                index_name=project.model.name,
                metadata_fields=["source", "keywords"],
                index_prefix="llama_" + project.model.name,
                overwrite=False)

            storage_context = StorageContext.from_defaults(
                vector_store=vector_store)
            index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context, embed_model=brain.getEmbedding(project.model.embeddings))
            return index
        else:
            return vector_load(brain, project)


def vector_save(project):
    if project.model.vectorstore == "chroma":
        pass
    elif project.model.vectorstore == "redis":
        try:
            project.db.vector_store.persist(persist_path="")
        except BaseException:
            print("REDIS - Error saving vectors")


def vector_load(brain, project):
    if project.model.vectorstore == "chroma":
        return vector_init(brain, project)
    if project.model.vectorstore == "redis":
        vector_store = RedisVectorStore(
            redis_url="redis://" +
            os.environ["REDIS_HOST"] +
            ":" +
            os.environ["REDIS_PORT"],
            index_name=project.model.name,
            metadata_fields=["source", "keywords"],
            index_prefix="llama_" + project.model.name,
            overwrite=False)
        return VectorStoreIndex.from_vector_store(embed_model=brain.getEmbedding(
            project.model.embeddings), vector_store=vector_store)


def vector_list(project):
    output = []
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)

        docs = collection.get(
            include=["metadatas"]
        )

        index = 0
        for metadata in docs["metadatas"]:
            if metadata["source"] not in output:
                output.append(metadata["source"])
            index = index + 1

    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys("llama_" + project.model.name + "/*")
        for key in keys:
            source = lredis.hget(key, "source")
            if source not in output:
                output.append(source)

    return {"embeddings": output}


def vector_list_source(project, source):
    output = []
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)

        docs = collection.get(
            include=["metadatas"]
        )

        index = 0
        for metadata in docs["metadatas"]:
            if metadata["source"] == source:
                output.append(metadata["source"])
            index = index + 1

    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys("llama_" + project.model.name + "/*")
        for key in keys:
            sourcer = lredis.hget(key, "source").strip()
            id = lredis.hget(key, "id").strip()
            if source == sourcer:
                output.append({"source": source, "id": id, "score": 1})

    return output


def vector_info(project):
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)

        docs = collection.get(
            include=["metadatas"]
        )
        return len(docs["ids"])
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys("llama_" + project.model.name + "/*")
        return len(keys)


def vector_find_source(project, source):
    docs = []
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)
        docs = collection.get(where={'source': source})
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys("llama_" + project.model.name + "/*")
        ids = []
        metadatas = []
        documents = []
        for key in keys:
            lsource = lredis.hget(key, "source")
            if lsource == source:
                ids.append(key)
                metadatas.append(
                    {"source": lsource, "keywords": lredis.hget(key, "keywords")})
                documents.append(lredis.hget(key, "text"))

        docs = {"ids": ids, "metadatas": metadatas, "documents": documents}

    return docs


def vector_find_id(project, id):
    output = {"id": id}
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)
        docs = collection.get(ids=[id])
        output["metadata"] = {
            k: v for k, v in docs["metadatas"][0].items() if not k.startswith('_')}
        output["document"] = docs["documents"][0]
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        ids = "llama_" + project.model.name + "/vector_" + id
        keys = lredis.hkeys(ids)
        keys = [k for k in keys if not k.startswith(
            '_') and k != "vector" and k != "text" and k != "doc_id" and k != "id"]
        data = lredis.hmget(ids, keys)
        text = lredis.hget(ids, "text")
        output["metadata"] = dict(zip(keys, data))
        output["document"] = text

    return output


def vector_delete(project):
    if project.model.vectorstore == "chroma":
        try:
            embeddingsPath = FindEmbeddingsPath(project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        try:
            lredis.ft(project.model.name).dropindex(True)
            embeddingsPath = FindEmbeddingsPath(project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass


def vector_delete_source(project, source):
    ids = []
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)
        ids = collection.get(where={'source': source})['ids']
        if len(ids):
            collection.delete(ids)
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys("llama_" + project.model.name + "/*")
        for key in keys:
            lsource = lredis.hget(key, "source")
            if lsource == source:
                ids.append(key)
                lredis.delete(key)
    return ids


def vector_delete_id(project, id):
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        collection = db.get_or_create_collection(project.model.name)
        ids = collection.get(ids=[id])['ids']
        if len(ids):
            collection.delete(ids)
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        lredis.delete(id)
    return id


def vector_reset(brain, project):
    if project.model.vectorstore == "chroma":
        path = FindEmbeddingsPath(project.model.name)
        db = chromadb.PersistentClient(path=path)
        db.reset()
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        lredis.ft(project.model.name).dropindex(True)

    project.db = vector_init(brain, project)
