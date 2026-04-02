import math
import shutil
import chromadb
import uuid

from restai.vectordb.tools import find_embeddings_path
from restai.config import CHROMADB_HOST, CHROMADB_PORT

# Reuse PersistentClient per cache path within the same worker process.
_cache_client_cache = {}


def _get_cache_client(path):
    if CHROMADB_HOST:
        return chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
    if path not in _cache_client_cache:
        _cache_client_cache[path] = chromadb.PersistentClient(path=path)
    return _cache_client_cache[path]


class Cache:

    def __init__(self, project):
        self.project = project
        cache_path = find_embeddings_path(self.project.props.name + "_cache")
        self.client = _get_cache_client(cache_path)
        self.collection = self.client.get_or_create_collection(
            name=self.project.props.name + "_cache"
        )

    def verify(self, question):
        results = self.collection.query(
            query_texts=[question],
            n_results=1,
            include=["metadatas", "documents", "distances"],
        )

        if len(results["ids"][0]) == 0:
            return None

        distance = math.exp(-results["distances"][0][0])
        threshold = self.project.props.options.cache_threshold
        if threshold is None:
            threshold = 0.85

        if distance > threshold:
            metadata = results["metadatas"][0][0]
            return metadata["answer"]

        return None

    def add(self, question, answer):
        self.collection.add(
            documents=[question],
            metadatas=[{"question": question, "answer": answer}],
            ids=[str(uuid.uuid4())],
        )
        return True

    def clear(self):
        """Clear all cached entries without deleting the cache itself."""
        try:
            self.client.delete_collection(self.project.props.name + "_cache")
            self.collection = self.client.get_or_create_collection(
                name=self.project.props.name + "_cache"
            )
        except Exception:
            pass

    def count(self):
        """Return the number of cached entries."""
        return self.collection.count()

    def delete(self):
        try:
            cache_path = find_embeddings_path(self.project.props.name + "_cache")
            shutil.rmtree(cache_path, ignore_errors=True)
            _cache_client_cache.pop(cache_path, None)
        except BaseException:
            pass
