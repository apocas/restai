from abc import ABC, abstractmethod
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from restai.brain import Brain
from restai.project import Project

class VectorBase(ABC):
    index: BasePydanticVectorStore = None
    project: Project = None

    def __init__(self, brain: Brain, project: Project, embedding):
        """Shared preamble for every backend.

        `store_key` lives here so a backend cannot accidentally name its storage
        after the project's mutable, lossily-sanitized name — the bug this
        replaced. Backends derive their own naming form FROM `self.store_key`.
        """
        from restai.vectordb.tools import project_store_key

        self.project = project
        self.embedding = embedding
        self.store_key = project_store_key(project)


    @abstractmethod
    def save(self):
        pass
      
    @abstractmethod
    def load(self, brain: Brain):
        pass

    @abstractmethod
    def list(self):
        pass

    @abstractmethod
    def list_source(self, source):
        pass

    @abstractmethod
    def info(self):
        pass

    @abstractmethod
    def find_source(self, source):
        pass

    @abstractmethod
    def find_id(self, id):
        pass

    @abstractmethod
    def delete(self):
        pass

    @abstractmethod
    def delete_source(self, source):
        pass

    @abstractmethod
    def delete_id(self, id):
        pass

    @abstractmethod
    def reset(self, brain):
        pass

    def list_all_chunks(self, limit=50000):
        """Return all chunks as list of {"id": str, "source": str, "text": str}."""
        return []