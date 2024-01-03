import os
import shutil
from langchain.vectorstores import Chroma
from llama_index import ServiceContext, StorageContext, VectorStoreIndex
import redis

from app.tools import FindEmbeddingsPath
from llama_index.vector_stores import RedisVectorStore


def vector_init(brain, project):
    path = FindEmbeddingsPath(project.model.name)

    if project.model.vectorstore == "chroma":
        return Chroma(
            persist_directory=path, embedding_function=brain.getEmbedding(
                project.model.embeddings))
    elif project.model.vectorstore == "redis":
        if path is None or len(os.listdir(path)) == 0:
            vector_store =  RedisVectorStore(
                redis_url="redis://" +
                os.environ["REDIS_HOST"] +
                ":" +
                os.environ["REDIS_PORT"],
                index_name=project.model.name,
                metadata_fields=["source", "keywords"],
                index_prefix="llama_" + project.model.name,
                overwrite=False)
        
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            service_context = ServiceContext.from_defaults(embed_model=brain.getEmbedding(
                project.model.embeddings))
            index = VectorStoreIndex.from_vector_store(
                vector_store, storage_context=storage_context, service_context=service_context)
            
            return index
        else:
            return vector_load(brain, project)


def vector_save(project):
    if project.model.vectorstore == "chroma":
        project.db.persist()
    elif project.model.vectorstore == "redis":
        try:
            project.db.vector_store.persist(persist_path="")
        except BaseException:
            print("REDIS - Error saving vectors")


def vector_load(brain, project):
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
        service_context = ServiceContext.from_defaults(embed_model=brain.getEmbedding(
                project.model.embeddings))
        return VectorStoreIndex.from_vector_store(vector_store=vector_store, service_context=service_context)


def vector_list(project):
    output = []
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")

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
        collection = project.db._client.get_collection("langchain")

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
            sourcer = lredis.hget(key, "source")
            if source == sourcer:
                output.append(sourcer)

    return output


def vector_info(project):
    if project.model.vectorstore == "chroma":
        dbInfo = project.db.get()
        return len(dbInfo["documents"]), len(dbInfo["metadatas"])
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        keys = lredis.keys("llama_" + project.model.name + "/*")
        return len(keys), len(keys)


def vector_find_source(project, source):
    docs = []
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
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
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
        docs = collection.get(ids=[id])

    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        lsource = lredis.hgetall("llama_" + project.model.name + "/" + id, "source")
    return id


def vector_delete(project):
    if project.model.vectorstore == "chroma":
        try:
            embeddingsPath = FindEmbeddingsPath(project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass
    elif project.model.vectorstore == "redis":
        project.db.drop_index(project.model.name, delete_documents=True, redis_url="redis://" +
                              os.environ["REDIS_HOST"] +
                              ":" +
                              os.environ["REDIS_PORT"])
        try:
            embeddingsPath = FindEmbeddingsPath(project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass


def vector_delete_source(project, source):
    ids = []
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
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
            if lsource == source or lsource == os.path.join(
                    os.environ["UPLOADS_PATH"], project.model.name, source):
                ids.append(key)
                lredis.delete(key)
    return ids


def vector_delete_id(project, id):
    if project.model.vectorstore == "chroma":
        collection = project.db._client.get_collection("langchain")
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
        project.db._client.reset()
    elif project.model.vectorstore == "redis":
        lredis = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=os.environ["REDIS_PORT"],
            decode_responses=True)
        lredis.ft(project.model.name).dropindex(True)

    project.db = vector_init(brain, project)
