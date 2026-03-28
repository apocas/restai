import math
import shutil
import chromadb
import uuid

from restai.vectordb.tools import find_embeddings_path


class Cache:

    def __init__(self, project):
        self.project = project
        self.client = chromadb.PersistentClient(
            path=find_embeddings_path(self.project.props.name + "_cache")
        )
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
            embeddingsPath = find_embeddings_path(self.project.props.name + "_cache")
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass
